#!/usr/bin/python3
# -*- coding: utf-8 -*-
from datetime import datetime
from elasticsearch import Elasticsearch
import json
import argparse
import sys, time
import os.path
import signal
import codecs
import syslog
import socket
import threading
import urllib3.request
from multiprocessing import Pool
from multiprocessing import Lock
sys.path.append('~/slub-lod-elasticsearch-tools/')
from es2json import esgenerator
from es2json import esgenerator
from daemon import Daemon

es=None
args=None
ppn=None

schema2entity = {
    "forename":"givenName",
    "surname":"familyName",
    "professionorOccupation":"hasOccupation",
    "dateOfDeath":"deathDate",
    "dateOfBirth":"birthDate",
    "placeOfBirth":"birthPlace",
    "sameAs":"sameAs"
}


def push_ppns(host,port,ppns): #expecting a python-array here!
    message=json.dumps(ppn)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host,port))
    sock.send(message.encode('utf-8'))
    sock.close()
    


def entityfacts(record):
    changed=False
    if 'sameAs' in record:
        if "http://d-nb.info/gnd/" in record['sameAs']:
            http = urllib3.PoolManager()
            url="http://hub.culturegraph.org/entityfacts/"+str(record['sameAs'].split('/')[-1])
            r=http.request('GET',url)
            try:
                data = json.loads(r.data.decode('utf-8'))
            except:
                return [0,0]
            for k,v in schema2entity.items():
                    if k=="sameAs":
                        if isinstance(record['sameAs'],str):
                            dnb=record['sameAs']
                            record['sameAs']=[dnb]
                        if k in data:
                            if v not in record:
                                record[v]=data[k]["@id"]
                                changed=True
                            else:
                                for sameAs in data[k]:
                                    record[v].append(sameAs["@id"])
                                    changed=True
                    if k in data and v not in record:
                        record[v]=data[k]
                        changed=True
                    elif k in data and v in record and k!="sameAs":
                        if k=="dateOfDeath" or k=="dateOfBirth":
                            if data[k]!=record[v] and record[v] and data[k]:
                                if record[v] in data[k]:
                                    record[v]=data[k]
                                elif k in record:
                                    syslog.syslog("Error! "+record["@id"]+" birthDate in SWB differs from entityFacts! SWB: "+record["birthDate"]+" EF: "+data["dateOfBirth"])
    if changed:
        return record
    else:
        return [0,0]

def process_stuff(jline):
    length=len(jline.items())
    body=entityfacts(jline)
    if (len(body) > length):
        es.index(index=args.index,doc_type=args.type,body=body,id=body["identifier"])
        return

def update_by_ppn(ppn):
    process_stuff(es.get(index=args.index,doc_type=args.type,id=ppn)["_source"])

def update_ppns(ppns):
    pool = Pool(8)
    pool.map(update_by_ppn,ppns)
    #for ppn in ppns:
        
        #update_by_ppn(ppn)
        
class ThreadedServer(object):
    def __init__(self,host,port):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.sock.bind((self.host,self.port))
        
    def listen(self):
        self.sock.listen(5)
        while True:
            try:
                client, address = self.sock.accept()
                syslog.syslog("connection from "+str(address))
                client.settimeout(60)
                t = threading.Thread(target = self.listenToClient, args = (client,address))
                t.start()
                t.join()
                client.close()
            finally:
                client.close()
            
    def listenToClient(self,client,address):
        size=1024
        message=""
        ppn=None
        while True:
            try:
                data=client.recv(size)
                if data:
                    message+=data.decode('utf-8')   # we expect a json-array
                if not data:
                    try:
                        ppn=json.loads(message)
                    except:
                        syslog.syslog("json error")
                    data=None
                    syslog.syslog("going to update "+str(len(ppn))+" PPNs got from "+ str(address))
                    s = threading.Thread(target = self.update,args=([ppn]))
                    s.start()
                    client.close()
                    break    
            except:
                client.close()
        client.close()
    
    def update(self,ppns):
        update_ppns(ppns)
    
class entityfactsd(Daemon):
    def run(self): 
        if args.full_index:
            pool = Pool(16)
            pool.map(process_stuff, esgenerator(host=args.host,port=args.port,type=args.type,index=args.index,headless=True))
        else:
            ThreadedServer(args.address,args.socketport).listen()
            
        
        

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description='enrich your ElasticSearch Search Index with data from entityfacts!')
    parser.add_argument('-host',type=str,help='hostname or IP-Address of the ElasticSearch-node to use.')
    parser.add_argument('-port',type=int,help='Port of the ElasticSearch-node to use, default is 9200.')
    parser.add_argument('-type',type=str,help='ElasticSearch Index to use')
    parser.add_argument('-index',type=str,help='ElasticSearch Type to use')
    parser.add_argument('-file',type=str,help='File with line-delimited IDs to update')
    parser.add_argument('-start',action='store_true',help='start a deaemon to listen on a socket to receive SWB-PPN to update')
    parser.add_argument('-stop',action='store_true',help='stop to listen on a socket to receive SWB-PPN to update')
    parser.add_argument('-restart',action='store_true',help='start a deaemon to listen on a socket to receive SWB-PPN to update')
    parser.add_argument('-full_index',action="store_true",help='update full index')
    parser.add_argument('-listen',action="store_true",help='listen for PPNs')
    parser.add_argument('-debug',action="store_true",help='no deaemon')
    parser.add_argument('-pid_file',type=str,help="Path to store the pid_file of the daemon")
    parser.add_argument('-conf',type=str,help='Daemon config file')
    parser.add_argument('-address',type=str,default="127.0.0.1",help='address of the interface to listen to')
    parser.add_argument('-socketport',type=int,help='port to listen for')
    args=parser.parse_args()
    if args.conf:
        with open(args.conf,'r') as cfg:
            config = json.loads(cfg.read().replace('\n',''))
            if not args.index and not 'index' in config:
                sys.stderr.write("no ElasticSearch index defined in config or -index parameter. exiting.\n")
                exit(-1)
            elif not args.index and 'index' in config:
                args.index=config['index']
                
            if not args.type and not 'type' in config:
                sys.stderr.write("no ElasticSearch doc type defined in config -type parameter. exiting\n")
                exit(-1)
            elif not args.type and 'type' in config:
                args.type=config['type']
                
            if not args.host and not 'host' in config:
                sys.stderr.write("no elasticsearch host defined in config or -host parameter. exiting\n")
                exit(-1)
            elif not args.host and 'host' in config:
                args.host = config['host']
            
            if not args.port and not 'port' in config:
                sys.stderr.write("no elasticsearch port defined in config or -host parameter. exiting\n")
                exit(-1)
            elif not args.port and 'port' in config:
                args.port = config['port']
                
            if not args.address and not 'ef_host' in config:
                sys.stderr.write("no ef_host defined in config or -address parameter. exiting\n")
                exit(-1)
            elif not args.address and 'ef_host' in config:
                args.address=config['ef_host']
            
            if not args.socketport and not 'ef_port' in config:
                sys.stderr.write("no ef_port defined in config or -socketport parameter. exiting\n")
                exit(-1)
            elif not args.socketport and 'ef_port' in config:
                args.socketport=int(config['ef_port'])
                
            if args.start or args.stop or args.restart:
                if not args.pid_file and not 'pid_file' in config:
                    sys.stderr.write("no pid_file defined in config or paramter. exiting\n")
                    exit(-1)
                if not args.pid_file and 'pid_file' in config:
                    args.pid_file=config['pid_file']
                    
    es=Elasticsearch([{'host':args.host}],port=args.port)
    if args.start:
        daemon = entityfactsd(args.pid_file)
        daemon.start()
    elif args.stop:
        daemon = entityfactsd(args.pid_file)
        daemon.stop()
    elif args.restart:
        daemon = entityfactsd(args.pid_file)
        daemon.restart()
    elif args.debug:
        entityfactsd(args.pid_file).run()
    elif args.file:
        with codecs.open(args.file,'r',encoding='utf-8') as f: #use with parameter to close stream after context
            ppns=[]
            for line in f:
                try:
                    ppns.append(str(line).strip())
                except:
                    pass
            update_ppns(ppns)
    else:
        pass
