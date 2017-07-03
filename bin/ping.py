#/usr/bin/env python
#-*-coding:utf8-*-

"""
@version: 0.9
@Author: Seven
$Contact: lingjie@gyyx.cn
"""

import os, sys, time
import json, urllib, urllib2, socket, struct, dpkt, fcntl, threading, syslog, Queue
from xml.dom import minidom

SIG_NUMS = 1
ret_at_1s = {}
REQUEST = ''
GET_IP_SLEEP_TIME = 60#s
PID = os.getpid()
BUFF_SIZE = 128
ICMP_REPLY = 0
ROOT = os.path.dirname(os.path.dirname(__file__))
TRACE_PATH = '%s/bin/traceroute'%ROOT
SEQ = 0
IFNAME = 'eth0'

def w_log(string):
	syslog.syslog(syslog.LOG_ERR, string)

def initcfg(xmlpath):
	cfg = {}
	target = ["Server", "Port", "Path", "Times", "Interval"]
	xmldoc  = minidom.parse(xmlpath)
	xmlroot = xmldoc.firstChild
	for tag in target:
		cfg[tag] = xmlroot.getElementsByTagName(tag)[0].childNodes[0].nodeValue
	return cfg

def url_request(url, data):
	response = urllib2.urlopen(urllib2.Request(url, urllib.urlencode(data)))
	ret = response.read()
	response.close()
	return ret

def get_ipaddress(ifname = 'eth0'):
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('24s',ifname))[20:24])

def getxml(filename):
	xmldoc = minidom.parse(filename)
	return xmldoc

def makexml():
	impl = minidom.getDOMImplementation()
	xmldoc = impl.createDocument(None, 'ping', None)
	return xmldoc

class Trace(threading.Thread):
	def __init__(self, dst, uptime):
		super(Trace, self).__init__()
		self.setDaemon(True)
		self.dst = dst
		self.uptime = uptime
		
	def run(self):
		DIR = "%s/%s"%(TRACE_PATH, self.dst)
		if not os.path.exists(DIR):
			os.makedirs(DIR)
		
		fp = os.popen("traceroute -n -w 1 %s -s %s"%(self.dst, get_ipaddress(IFNAME)))
		ret = fp.read()
		fp.close()

		try:
			fp = open("%s/%s"%(DIR, time.strftime("%Y%m%d%H%M%S", time.localtime(self.uptime))[:-1] + '0'), 'w')
		except Exception, e:
			w_log("Open file %s error, msg: %s"%("%s/%s"%(DIR, time.strftime("%Y%m%d%H%M%S", time.localtime(self.uptime))), str(e.args)))
			return False
		
		fp.write(ret)
		fp.close()

class Send(threading.Thread):
	def __init__(self, event, lock):
		super(Send, self).__init__()
		self.setDaemon(True)
		self.src_addr = get_ipaddress(IFNAME)
		self.event = event
		self.lock = lock

	def run(self):
		ip_src = socket.inet_aton(self.src_addr)
		sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
		sock.bind((self.src_addr, 0))
		sock.setsockopt(socket.SOL_IP, socket.IP_HDRINCL, 1)
		while True:
			self.event.wait()
			self.lock.acquire()
			req = json.loads(REQUEST)
			self.lock.release()    
			for i in req:
				try:
					ip_dst = socket.inet_aton(i)
					ip = dpkt.ip.IP(src = ip_src, dst = ip_dst, p = 1, ttl = 255)
					icmp = dpkt.icmp.ICMP(type = 8, data = dpkt.icmp.ICMP.Echo(id = PID, seq = SEQ, data = repr(time.time())))
					ip.data = icmp
					ip.len += len(ip.data)
					sock.sendto(str(ip), (i, 0))
				except Exception, e:
					try:
						w_log(json.dumps(e.args))
					except:
						pass

			self.event.clear()

class Recv(threading.Thread):
	def __init__(self, lock):
		super(Recv, self).__init__()
		self.setDaemon(True)
		self.lock = lock
		self.src_addr = get_ipaddress(IFNAME)

	def run(self):
		sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
		sock.bind((self.src_addr, 0))
		sock.setsockopt(socket.SOL_IP, socket.IP_HDRINCL, 1)
		while True:
			try:
				tmp, addr = sock.recvfrom(BUFF_SIZE)
				content = dpkt.ip.IP(tmp)
				if content.data.type == ICMP_REPLY and content.data.data.id == PID and content.data.data.seq == SEQ:
					cast_time = (time.time() - float(content.data.data.data)) * 1000#ms
					if cast_time > 1000:
						cast_time = 0
					self.lock.acquire()
					ret_at_1s.setdefault(addr[0], []).append(cast_time)
					self.lock.release()
			except Exception, e:
				try:
					w_log(json.dumps(e.args))
				except:
					pass

class SigHandle(threading.Thread):
	def __init__(self, lock1, lock2, que):
		super(SigHandle, self).__init__()
		self.setDaemon(True)
		self.lock1 = lock1
		self.lock2 = lock2
		self.que = que

	def run(self):
		global ret_at_1s, REQUEST
		while True:
			uptime = self.que.get(block = True)
			delayinfo = {}
			self.lock2.acquire()
			ret = ret_at_1s
			ret_at_1s = {}
			self.lock2.release()       
			updatetime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(uptime))
			filename = '%s/bin/static/data_'%ROOT+ time.strftime('%Y%m%d%H%M', time.localtime(uptime)) +'.xml'
			if not os.path.exists(os.path.dirname(filename)):
				os.mkdir(os.path.dirname(filename))
			self.lock1.acquire()
			req = json.loads(REQUEST)
			self.lock1.release()
			for i in req:
				tmp = ret.get(i, 0)
				if tmp == 0:
					delayinfo[i] = {"delay": "0", "timeout": "10", "updatetime": updatetime}
				else:
					delayinfo[i] = {"delay": "%0.2f" % (sum(tmp) / len(tmp)), "timeout": str(abs(10 - len(tmp))), "updatetime": updatetime}
				
				if int(delayinfo[i]['timeout']) > 0:
					Trace(i, uptime).start()

			for key, info in delayinfo.iteritems():
				if os.path.exists(filename):
					xmldoc = getxml(filename)
				else:
					xmldoc = makexml()

				xmlroot = xmldoc.firstChild       
				dst = xmldoc.createElement('dst')
				
				ip = xmldoc.createElement('ip')
				ip.appendChild(xmldoc.createTextNode(key))
				dst.appendChild(ip)
				
				delay = xmldoc.createElement('delay')
				delay.appendChild(xmldoc.createTextNode(info['delay']))
				dst.appendChild(delay)
				
				uptime = xmldoc.createElement('updatetime')
				uptime.appendChild(xmldoc.createTextNode(info['updatetime']))
				dst.appendChild(uptime)
				
				timeout = xmldoc.createElement('timeout')
				timeout.appendChild(xmldoc.createTextNode(info['timeout']))
				dst.appendChild(timeout)
				
				xmlroot.appendChild(dst)
				
				f = open(filename, 'w')
				xmldoc.writexml(f, encoding='utf-8')
				f.close()

class GetIP(threading.Thread):
	def __init__(self, lock):
		super(GetIP, self).__init__()
		self.setDaemon(True)
		self.lock = lock
	
	def run(self):
		global REQUEST
		while True:
			local_addr = get_ipaddress(IFNAME)
			cfg = initcfg("%s/etc/ping.xml"%ROOT)
			try:
				request = url_request("http://" + cfg["Server"] + ":" + cfg["Port"] + cfg["Path"] + "ping.php?act=get_ip", {"ip": local_addr})
				fp = file('%s/etc/pinglist.py'%ROOT,'w')
				fp.write(request)
				fp.close()
			
			except Exception:
				w_log("Can not connect %s" % cfg["Server"])
				fp = open('%s/etc/pinglist.py'%ROOT,'r')
				request = fp.read()
				fp.close()

				if request != REQUEST:
					try:
						json.loads(request)
						self.lock.acquire()
						REQUEST = request
						self.lock.release()
					except:
						w_log("json load %s error"%request)
				
			time.sleep(GET_IP_SLEEP_TIME)

def daemon():
	os.umask(0)
	
	pid = os.fork()        
	if pid > 0:
		sys.exit(0)
	
	os.setsid()
	pid = os.fork()
	if pid > 0:
		sys.exit(0)
	
	for i in range(1024):
		try:
			os.close(i)
		except:
			continue
	
	sys.stdin = open("/dev/null", "w+")
	sys.stdout = sys.stdin
	sys.stderr = sys.stdin

if __name__ == "__main__":
	daemon()
	syslog.openlog("Ping", 0, syslog.LOG_LOCAL6)
	offon = Queue.Queue()
	lock_on_req = threading.RLock()
	lock_on_ret = threading.RLock()
	event = threading.Event()
	
	ip = GetIP(lock_on_req)
	ip.start()
	
	time.sleep(3)
	
	send = Send(event, lock_on_req)
	send.start()
	
	recv = Recv(lock_on_ret)
	recv.start()
	
	sig = SigHandle(lock_on_req, lock_on_ret, offon)
	sig.start()
	
	START = time.time()
	SLEEP_TIME = 1

	while True:
		print time.asctime()
		event.set()
		time.sleep(SLEEP_TIME)
		
		if SIG_NUMS >= 10:
			START += 10
			tmp = time.time() - START
			print tmp
			if tmp > 1:
				SLEEP_TIME = (10 - tmp) / 10
			else:
				SLEEP_TIME = 1
			if SLEEP_TIME < 0.1:
				SLEEP_TIME = 0.1
		
			offon.put(START)
			SIG_NUMS = 0
			if SEQ >= 65535:
				SEQ = 0
			else:
				SEQ += 1
		SIG_NUMS += 1
	syslog.closelog()