#!/usr/bin/python3

import argparse
import json
import requests
from es2json import esgenerator,isint,litter,eprint
from rdflib import Graph


if __name__ == "__main__":
    i=0
    j=0
    parser=argparse.ArgumentParser(description='enrich ES by WD!')
    parser.add_argument('-host',type=str,default="127.0.0.1",help='hostname or IP-Address of the ElasticSearch-node to use, default is localhost.')
    parser.add_argument('-port',type=int,default=9200,help='Port of the ElasticSearch-node to use, default is 9200.')
    parser.add_argument('-index',type=str,help='ElasticSearch Search Index to use')
    parser.add_argument('-type',type=str,help='ElasticSearch Search Index Type to use')
    parser.add_argument("-id",type=str,help="retrieve single document (optional)")
    parser.add_argument('-server',type=str,help="use http://host:port/index/type/id?pretty. overwrites host/port/index/id/pretty") #no, i don't steal the syntax from esbulk...
    args=parser.parse_args()
    if args.server:
        slashsplit=args.server.split("/")
        args.host=slashsplit[2].rsplit(":")[0]
        if isint(args.server.split(":")[2].rsplit("/")[0]):
            args.port=args.server.split(":")[2].split("/")[0]
        args.index=args.server.split("/")[3]
        if len(slashsplit)>4:
            args.type=slashsplit[4]
        if len(slashsplit)>5:
            if "?pretty" in args.server:
                args.pretty=True
                args.id=slashsplit[5].rsplit("?")[0]
            else:
                args.id=slashsplit[5]
    url="https://query.wikidata.org/bigdata/namespace/wdq/sparql"
    for rec in esgenerator(host=args.host,port=args.port,index=args.index,type=args.type,headless=True,body={"query":{"match_phrase":{"sameAs":"http://d-nb.info"}}}):
        i=i+1
        gnd=None
        if rec.get("sameAs"):
            if isinstance(rec.get("sameAs"),list) and any("http://d-nb.info" for x in rec.get("sameAs")):
                for item in rec.get("sameAs"):
                    if "http://d-nb.info" in item and len(item.split("/"))>4:
                        gnd=item.split("/")[4]
            elif isinstance(rec.get("sameAs"),str) and "http://d-nb.info" in rec.get("sameAs"):
                gnd=rec.get("sameAs").split("/")[4]
        if gnd:
            query='''
            PREFIX wikibase: <http://wikiba.se/ontology#>
            PREFIX wd: <http://www.wikidata.org/entity/>
            PREFIX wdt: <http://www.wikidata.org/prop/direct/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            
            SELECT ?person
            WHERE {
                ?person wdt:P227  "'''+str(gnd)+'''" .
            SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
            }'''
            data=requests.get(url,params={'query':query,'format':'json'}).json()
        
            #if len(data.get("results").get("bindings"))>0:
            #    for item in data.get("results").get("bindings"):
            #            allprops=requests.get("https://www.wikidata.org/w/api.php?action=wbgetentities&ids={identifier}&format=json".format(identifier=item.get("person").get("value").split("/")[-1])).json()
            #            if isinstance(allprops,dict) and "entities" in allprops:
            #                for entity in allprops.get("entities"):
            #                    if "claims" in allprops.get("entities").get(entity):
            #                        for p in allprops.get("entities").get(entity).get("claims"):
           #                             for i,elem in enumerate(allprops["entities"][entity]["claims"][p]):
            #                                for toClean in ["qualifiers","mainsnak","references"]:
            #                                    if toClean in allprops["entities"][entity]["claims"][p][i]:
            #                                        allprops["entities"][entity]["claims"][p][i].pop(toClean)
            #                    if "id" in allprops.get("entities").get(entity).get("claims"):
            #                        print(json.dumps(allprops.get("entities").get(entity).get("claims").get("id"),indent=None))
            try:
                data=requests.get(url,params={'query':query,'format':'json'}).json()
                if len(data.get("results").get("bindings"))>0:
                    for item in data.get("results").get("bindings"):
                        rec["sameAs"]=litter(rec["sameAs"],item.get("person").get("value"))
                        #j=j+1
                        #print("record nr {i}, Wikidata_ID {id} nr {j}".format(i=i,j=j,id=item.get("person").get("value")))
                        print(json.dumps(rec,indent=None))
            except:
                continue
                
            
