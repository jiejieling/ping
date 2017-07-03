#/usr/bin/env python
#-*-coding:utf8-*-

import MySQLdb,datetime

def conn():
    conn=MySQLdb.connect(host = "115.182.1.142", user = "ping", passwd = "_HN]Ukw)h51J;6", db = "idc_ping_monitor")
    conn.autocommit(True)
    return conn

if __name__ == "__main__":
    db = conn()
    cur = db.cursor()
    
    '''删除数据'''
    current = datetime.datetime.now()
    ten_ago = current - datetime.timedelta(minutes = 30)
    sql = "DELETE FROM ping_excute WHERE do_time < '%s' or flag = 1" % ten_ago.strftime('%Y-%m-%d %H:%M')
    cur.execute(sql)
      
    '''添加'''
    sql = "SELECT ip FROM ping WHERE is_del = 0 ORDER BY id DESC"
    cur.execute(sql)
    ip_data = cur.fetchall()
    
    sql_in = "INSERT INTO ping_excute (src, do_time) VALUES('%s','%s')"
    current = datetime.datetime.now()
    do_time = (current - datetime.timedelta(minutes = 2))
    
    for ip in ip_data:
        param = (ip[0],do_time.strftime('%Y-%m-%d %H:%M'))
        cur.execute(sql_in%param)
    
    cur.close()
    db.close()