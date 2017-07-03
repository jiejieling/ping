#!/usr/bin/env python
#-*-coding:utf8-*-
'''
@attention: This is used for getting ping result, and insert into db
@license: GNU GPL v3
@author: Seven
@contact: lingjie@gyyx.cn
'''

from xml.dom.minidom import parseString
import sys, os, time, MySQLdb, datetime, syslog
import traceback
import httplib
from multiprocessing import Process

def w_log(string):
    syslog.syslog(syslog.LOG_ERR, string)

def conn():
    conn = MySQLdb.connect(host = "115.182.1.142", user = "ping", passwd = "_HN]Ukw)h51J;6", db = "idc_ping_monitor")
    conn.autocommit(True)
    return conn
    
def select(conn, sql):
    conn.execute(sql)
    return conn.fetchall()

def modify(conn, sql):
    conn.execute(sql)
    
def get_info_by_ip(db, ip,flag = 'src'):
    if flag == 'src':
        sql = "SELECT area,cname,c_alias FROM ping WHERE ip = '%s'"%ip
    else:
        sql = "SELECT area,cname,c_alias FROM ping WHERE switch = '%s'"%ip
    
    return select(db, sql)[0]

def url_request(url, ip, port, timeout = 5):
    for i in range(timeout):
        try:
            fp = httplib.HTTPConnection(ip, port, timeout = 2)
            fp.request('GET', url)
            response = fp.getresponse()
            if response.status == 200:
                return response.read()
        except:
            continue
    raise Exception, "visit %s time out"%url

def ReadXML(xmlPath) :
    xmlDoc=parseString(xmlPath)
    NodeList = []
    for tmp in xmlDoc.firstChild.childNodes:
        if tmp.nodeType == tmp.ELEMENT_NODE :
            TempList = []
            for nd in tmp.childNodes:
                if nd.nodeType == nd.ELEMENT_NODE:
                    ndName= nd.nodeName
                    ndValue= nd.firstChild.data
                    b=(ndName,ndValue)
                    TempList.append(b)
            NodeList.append(TempList)
    return NodeList

def save_ping_log(db, src, param):
    try:
        data_src = get_info_by_ip(db, src)
        data_dst = get_info_by_ip(db, param['ip'], 'dst')
    except:
        return False
    
    if data_src[0] not in ("双线", "BGP") and data_dst[0] not in  ("双线", "BGP") and data_src[0] != data_dst[0]:
        if int(param['timeout']) == 10:
            if not alarm.get(src, {}).get(param['ip'], False):
                modify(db, "insert into alarm(delay, threshold, src, dst) values(%f, %i, '%s', '%s')"%(float(param['delay']), int(param['timeout']), src, param['ip']))
                alarm.setdefault(src, {})[param['ip']] = [float(param['delay']), int(param['timeout'])]
            modify(db, "update alarm set flag = 1, delay = %f, threshold = %i, updatetime = '%s' where src = '%s' and dst = '%s'"%(float(param['delay']), int(param['timeout']), time.strftime("%Y/%m/%d %H:%M:%S"), src, param['ip']))
    else:
        if not alarm.get(src, {}).get(param['ip'], False):
            modify(db, "insert into alarm(delay, threshold, src, dst) values(%f, %i, '%s', '%s')"%(float(param['delay']), int(param['timeout']), src, param['ip']))
            alarm.setdefault(src, {})[param['ip']] = [float(param['delay']), int(param['timeout'])]
    
        if int(param['timeout']) >= 3: #or(float(param['delay']) - ths[src][param['ip']][0]) > 1 * ths[src][param['ip']][0]:
            sql1 = "update alarm set flag = 1, delay = %f, threshold = %i, updatetime = '%s' where src = '%s' and dst = '%s'"%(float(param['delay']), int(param['timeout']), time.strftime("%Y/%m/%d %H:%M:%S"), src, param['ip'])
            modify(db, sql1)
    sql = "INSERT INTO ping_log (src, dst, delay, timeout, updatetime) VALUES('%s','%s','%s','%s','%s') "
    updatetime = param['updatetime'][0:18]+"0";
    insert_param = (src,param['ip'], float(param['delay']), int(param['timeout']), updatetime)
    modify(db, sql%insert_param)
    return True

def save_timeout_log(db, src,param):
    updatetime = param['updatetime'][0:18]+"0";
    if True:
        sql = "INSERT INTO ping_timeout (src, dst, timeout, updatetime) VALUES ('%s','%s','%s','%s')"
        param_insert = (src, param['ip'], int(param['timeout']), updatetime)
        modify(db, sql%param_insert)
        
def save_ping_hour_log(db, src,tmpList, delay_arr):
    '''保存记录'''
    if not save_ping_log(db, src,tmpList):
        return False
    
    '''保存超时记录'''
    if int(tmpList['timeout']) > 0:
        save_timeout_log(db, src,tmpList)
    
    '''创建更新rrd文件'''
    rrdpath = "/home/htdocs/www/monitor/project/ping/rrd/" + src
    if not os.path.exists(rrdpath):
        os.makedirs(rrdpath)
        
    rrdname = rrdpath + '/' + tmpList['ip'] + '.rrd'
    rrdname2 = rrdpath + '/' + tmpList['ip'] + '_error.rrd'
    if delay_arr.get(tmpList['ip'], None) == None or delay_arr[tmpList['ip']] == 0.0:
        max_delay = 10
    else:
        max_delay = delay_arr[tmpList['ip']]
    
    updatetime = long(time.mktime(datetime.datetime.strptime(tmpList['updatetime'],'%Y-%m-%d %H:%M:%S').timetuple()))
    if not os.path.exists(rrdname):
        rrdcmd = 'rrdtool create %s ' % rrdname + \
            '--start %s --step 10 DS:ping:GAUGE:20:0:1000 RRA:MAX:0.5:1:720 RRA:MAX:0.5:6:1440 RRA:MAX:0.5:60:1440 RRA:MAX:0.5:360:1220' % (updatetime-60)
        os.system(rrdcmd)
    if not os.path.exists(rrdname2):
        rrdcmd = 'rrdtool create %s ' % rrdname2 + \
            '--start %s --step 10 DS:ping:GAUGE:20:0:1000 RRA:MAX:0.5:1:720 RRA:MAX:0.5:6:1440 RRA:MAX:0.5:60:1440 RRA:MAX:0.5:360:1220' % (updatetime-60)
        os.system(rrdcmd)
   
    if float(tmpList['delay']) > 0:
        rrdcmd = 'rrdtool update %s %s:%s' % (rrdname, updatetime, float(tmpList['delay']))
    else:
        rrdcmd = 'rrdtool update %s %s:%s' % (rrdname2, updatetime, max_delay)
    os.system(rrdcmd)
    
    rrdcmd = 'rrdtool update %s %s:%s' % (rrdname2, updatetime, max_delay * float(float(tmpList['timeout']) / 10))
    if int(tmpList['timeout']) > 0:
        os.system(rrdcmd)

def make_array(db, src, arr, delay_arr):
    ipList = {}
    temp_color = ''
    for key in arr:
        tmpList = {}
        for k in key:
            if k[0].strip() == 'ip':
                tmpList['ip'] = k[1].strip().encode('utf8')
                ipList.setdefault(tmpList['ip'], True)
            if k[0].strip() == 'delay':
                tmpList['delay'] = k[1].strip().encode('utf8')
            if k[0].strip() == 'updatetime':
                tmpList['updatetime'] = k[1].strip().encode('utf8')
                s_time = k[1].strip().encode('utf8')
            if k[0].strip() == 'timeout':
                tmpList['timeout'] = k[1].strip().encode('utf8')
        '''存储一个小时的记录'''
        save_ping_hour_log(db, src,tmpList,delay_arr)
    for ip in ipList:
        if ip == '219.238.232.196':
            graph_img(db, src,ip,s_time,temp_color)
        else:
            graph_img(db, src,ip,s_time)
    return True
    
def graph_img(db, src, dst,s_time,color=''):
    '''画图'''
    rrdpath = "/home/htdocs/www/monitor/project/ping/rrd/" + src    
    rrdname = rrdpath + '/' + dst + '.rrd'
    rrdname2 = rrdpath + '/' + dst + '_error.rrd'
    filepath = "/home/htdocs/www/monitor/project/ping/images/" + src
    
    if not os.path.exists(filepath):
        os.makedirs(filepath, 0777)
    
    filename = filepath + '/' + dst + '.gif'
    try: 
        data_src = get_info_by_ip(db, src)
        data_dst = get_info_by_ip(db, dst, flag = "dst")
    except:
        return False
    #设置字体
    fontname = '/usr/share/fonts/chinese/TrueType/simhei.ttf'
    titlename = '\"'+"[" + data_src[2] + "]" + "_" + src + '->' + "[" + data_dst[2] + "]" + "_" + dst + '\"'
    
    
    back_color = "#DDDDFF"
    if data_src[0] in ('双线', 'BGP') or data_dst[0] in ('双线', 'BGP'):
        back_color = "#BBFFFF"
    elif data_src[0] != data_dst[0]:
        back_color = "#FFFF6F"
    
    if color:
        back_color = color
        
    updatetime = long(time.mktime(datetime.datetime.strptime(s_time,'%Y-%m-%d %H:%M:%S').timetuple()))
        
    rrdcmd = 'rrdtool graph %s ' % filename + \
        '--font-render-mode light --lower-limit=0 --x-grid MINUTE:1:MINUTE:10:MINUTE:10:0:%H:%M ' + \
        '--start=%s --end=%s ' % (updatetime - 2400, updatetime) + \
        '-h 80 -w 240 -r -g ' + \
        'DEF:t1=%s:ping:MAX DEF:t2=%s:ping:MAX ' % (rrdname, rrdname2) + \
        '-n TITLE:8:%s -n AXIS:5:%s -n UNIT:5:%s -n LEGEND:5:%s ' % (fontname, fontname, fontname, fontname)+ \
        'AREA:t1#00CF00 AREA:t2#FF0000 --units-exponent=0 --alt-y-grid ' + \
        '--title %s --color BACK%s --color CANVAS#000000' % (titlename,back_color)
#    print rrdcmd 
    os.system(rrdcmd)

def update_flags(db, id):
    try:
        modify(db, "UPDATE ping_excute SET flag = 1 WHERE id = %i"%id)
        return 1
    except Exception:
        return 0
        
def zhuaqu(ip, other, delay_arr):
    syslog.openlog("Ping_get_xml", 0, syslog.LOG_LOCAL6)
    src = ip
    dst_data = other
    my_db = conn()
    my_cur = my_db.cursor()
    select(my_cur, "set names utf8")
    for dst in dst_data:
        log_flag = 0
        g_time_start = time.mktime(dst[0].timetuple())
        g_time = time.strftime('%Y%m%d%H%M',time.localtime(g_time_start))
        try:
            xml = url_request('http://%s:8888/static/data_%s.xml' % (src,g_time), src, 8888)
            arr = ReadXML(xml)
            log_flag = 1 
            if make_array(my_cur, src, arr, delay_arr):
                log_flag = 2
                if update_flags(my_cur, int(dst[1])):
                    url_request('http://%s:8888/delete?id=%s' % (src,g_time), src, 8888)
        except Exception, e:
            print traceback.print_exc()
            w_log("zhuaqu src: %s, log_flag : %i, msg: %s"%(src, log_flag, traceback.format_exc()))
            if (time.time() - g_time_start) >= 60:
                c_time = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
                modify(my_cur, "update alarm set flag = 1, threshold = 11, updatetime = '%s' where src = '%s'"%(c_time, src))
            #    for i in ips.keys():
            #        if i != src:
            #            graph_img(my_cur, src, i, c_time, "#FF0000")
            break
       
    my_cur.close()
    my_db.close()        
    syslog.closelog()
     
if __name__ == "__main__":
    for i in os.popen("ps aux |grep 'ping_get_xml.py'|grep -v grep|wc -l"):
        if int(i) > 17:
            sys.exit(1)
    
    db = conn()
    cursor=db.cursor()
    select(cursor, "set names utf8");
    #获取执行IP列表
    ips = {}
    for i in select(cursor, "SELECT src, do_time, id FROM ping_excute WHERE flag = 0 order by do_time"):
        ips.setdefault(i[0], []).append([i[1], i[2]])

    #获取报警信息列表
    alarm = {}
    for i in select(cursor, "select src, dst, delay, threshold from alarm"):
        alarm.setdefault(i[0], {}).setdefault(i[1], [i[2], i[3]])
        
    #获取最大延迟
    delay_arr = {}
    for i in select(cursor, "SELECT src, dst, MAX(delay) FROM ping_log GROUP BY src, dst"):
        delay_arr.setdefault(i[0], {}).setdefault(i[1], i[2])

    #重置报警
    modify(cursor, "update alarm set flag = 0, updatetime = '%s'"%time.strftime("%Y/%m/%d %H:%M:%S"))
    
    cursor.close()
    db.close()

    for ip, other in ips.items():
        Process(target = zhuaqu, args = (ip, other, delay_arr.get(ip, {}))).start()
