#!/usr/bin/env python

"""
Module to test RO SRS APIfunctions
"""

import os, os.path
import sys
import unittest
import logging
import json
import re
import StringIO
import httplib
import urlparse
import rdflib, rdflib.graph

from MiscLib import TestUtils

from ro_namespaces import RDF, RDFS, ORE, RO, DCTERMS, AO
from ROSRS_Session import ROSRS_Error, ROSRS_Session

# Logging object
log = logging.getLogger(__name__)

# Base directory for file access tests in this module
testbase = os.path.dirname(__file__)

# Test config details

class Config:
    ROSRS_API_URI = "http://sandbox.wf4ever-project.org/rodl/ROs/"
    #ROSRS_API_URI = "http://localhost:8080/ROs/"
    AUTHORIZATION = "47d5423c-b507-4e1c-8"

# Test cases

class TestApi_ROSRS(unittest.TestCase):

    def setUp(self):
        super(TestApi_ROSRS, self).setUp()
        self.rosrs = ROSRS_Session(Config.ROSRS_API_URI,
            accesskey=Config.AUTHORIZATION)
        return

    def tearDown(self):
        super(TestApi_ROSRS, self).tearDown()
        self.rosrs.close()
        return

    # Actual tests follow

    def testListROs(self):
        # Access RO SRS to list ROs: GET to ROSRS
        (status, reason, headers, data) = self.rosrs.doRequest("")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "text/plain")
        #self.assertEqual(headers["content-type"], "application/rdf+xml")
        if 0:
            print
            print "---- testListROs ----"
            print data
            print "----"
        return

    def testCreateRO(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestCreateRO/")
        # Create an RO: POST to ROSRS
        reqheaders   = {
            "slug":     "TestCreateRO"
            }
        roinfo = {
            "id":       "TestCreateRO",
            "title":    "Test create research object",
            "creator":  "TestAPI_ROSRS.py",
            "date":     "2012-06-27"
            }
        roinfotext = json.dumps(roinfo)
        if True:
            (status, reason, headers, manifest) = self.rosrs.doRequestRDF("",
                method="POST", reqheaders=reqheaders, body=roinfotext)
            self.assertEqual(status, 201)
            self.assertEqual(reason, "Created")
            self.assertEqual(headers["location"], self.rosrs.baseuri()+"TestCreateRO/")
            self.assertEqual(headers["content-type"], "application/rdf+xml")
            rouri = rdflib.URIRef(headers["location"])
        else:
            (status, reason, headers, manifest) = self.rosrs.doRequest("",
                method="POST", reqheaders=reqheaders, body=roinfotext)
            self.assertEqual(status, 201)
            self.assertEqual(reason, "Created")
            self.assertEqual(headers["location"], self.rosrs.baseuri()+"TestCreateRO/")
            rouri = rdflib.URIRef(headers["location"])
            (status, reason, headers, manifest) = self.rosrs.doRequestRDF(
                rouri, method="GET")
            self.assertEqual(status, 303)
            self.assertEqual(reason, "See Other")
            manifesturi = headers["location"]
            (status, reason, headers, manifest) = self.rosrs.doRequestRDF(
                manifesturi, method="GET")
            self.assertEqual(status, 200)
            self.assertEqual(reason, "OK")
            self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Check manifest RDF graph
        self.assertIn((rouri, RDF.type, RO.ResearchObject), manifest)
        # Test that new RO is in collection
        # Response is simple list of URIs (for now)
        rolist = self.rosrs.listROs()
        self.assertIn(str(rouri), [ r["uri"] for r in rolist ] )
        # Clean up
        self.rosrs.deleteRO("TestCreateRO/")
        return

    def testDeleteRO(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestDeleteRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestDeleteRO",
            "Test RO for deletion", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Test that new RO is in collection
        rolist = self.rosrs.listROs()
        self.assertIn(self.rosrs.baseuri()+"TestDeleteRO/", [ r["uri"] for r in rolist ] )
        # Delete an RO; locate proxy, delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="DELETE",
            accept="application/rdf+xml")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No Content")
        # Test that new RO is not in collection
        rolist = self.rosrs.listROs()
        self.assertNotIn(self.rosrs.baseuri()+"TestDeleteRO/", [ r["uri"] for r in rolist ] )
        return

    def testGetROManifest(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestGetRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        manifesturi = rdflib.URIRef(headers["location"])
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Check manifest RDF graph
        self.assertIn((rouri, RDF.type, RO.ResearchObject), manifest)
        self.assertIn((rouri, DCTERMS.creator, None), manifest)
        self.assertIn((rouri, DCTERMS.created, None), manifest)
        self.assertIn((rouri, ORE.isDescribedBy, manifesturi), manifest)
        # @@TODO: Id
        # @@TTODO: itle
        # @@TODO look for proxy in manifest
        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testGetROPage(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestGetRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO landing page
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="GET", accept="text/html")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        pageuri = rdflib.URIRef(headers["location"])
        (status, reason, headers, data) = self.rosrs.doRequest(pageuri,
            method="GET", accept="text/html")
        if status == 302:       # Moved temporarily
            pageuri = rdflib.URIRef(headers["location"])
            (status, reason, headers, data) = self.rosrs.doRequest(pageuri,
                method="GET", accept="text/html")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "text/html;charset=UTF-8")
        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testGetROZip(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestGetRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO content
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="GET", accept="application/zip")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        zipuri = rdflib.URIRef(headers["location"])
        (status, reason, headers, data) = self.rosrs.doRequest(zipuri,
            method="GET", accept="application/zip")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/zip")
        # @@TODO test content of zip (data)?
        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testAggregateResourceIntFull(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Aggegate internal resource: POST proxy ...
        reqheaders = { "slug": "test/path" }
        proxydata = ("""
            <rdf:RDF
              xmlns:ore="http://www.openarchives.org/ore/terms/"
              xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" >
              <ore:Proxy>
              </ore:Proxy>
            </rdf:RDF>
            """)
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy",
            reqheaders=reqheaders, body=proxydata)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        resuri   = links[str(ORE.proxyFor)]
        self.assertEqual(str(resuri),str(rouri)+"test/path")
        # ... try GET content
        (status, reason, headers, data) = self.rosrs.doRequest(resuri,
            method="GET", ctype="text/plain")
        self.assertEqual(status, 404)
        self.assertEqual(reason, "Not Found")
        # ... then PUT content
        rescontent = "Resource content\n"
        (status, reason, headers, data) = self.rosrs.doRequest(resuri,
            method="PUT", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(headers["location"], str(resuri))
        ####links    = self.rosrs.parseLinks(headers)
        ####self.assertEqual(links[str(ORE.proxyFor)], str(resuri))
        ####self.assertEqual(status, 200)
        ####self.assertEqual(reason, "OK")
        # Read manifest and check aggregated resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertIn( (rouri, ORE.aggregates, resuri), manifest )
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testAggregateResourceIntShort(self):
        # Aggegate internal resource (shortcut): POST content
        # Clean up from past runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Aggegate internal resource: POST content ...
        rescontent = "Resource content\n"
        reqheaders = { "slug": "test/path" }
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST", ctype="text/plain", body=rescontent,
            reqheaders=reqheaders)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        resuri   = links[str(ORE.proxyFor)]
        self.assertEqual(str(resuri),str(rouri)+"test/path")
        # Read manifest and check aggregated resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertIn( (rouri, ORE.aggregates, resuri), manifest )
        # GET content
        (status, reason, headers, data) = self.rosrs.doRequest(resuri,
            method="GET", ctype="text/plain")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(data, rescontent)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testDeleteResourceInt(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/path", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        log.debug("testDeleteResourceInt proxyuri: %s"%str(proxyuri))
        log.debug("testDeleteResourceInt   resuri: %s"%str(resuri))
        # Find proxy for resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        query = (
            "SELECT ?p WHERE "
              "{ ?p <%(proxyin)s> <%(rouri)s> ; <%(proxyfor)s> <%(resuri)s> }"%
            { "proxyin": ORE.proxyIn
            , "proxyfor": ORE.proxyFor
            , "rouri":    str(rouri)
            , "resuri":   str(resuri)
            })
        resp  = manifest.query(query)
        log.debug("testDeleteResourceInt query resp.bindings: %s"%(repr(resp.bindings)))
        proxyterms = [ b["p"] for b in resp.bindings ]
        self.assertEqual(len(proxyterms), 1)
        proxyuri = proxyterms[0]
        self.assertIsInstance(proxyuri, rdflib.URIRef)
        # Delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(proxyuri,
            method="DELETE")
        self.assertEqual(status, 307)
        self.assertEqual(reason, "Temporary Redirect")
        self.assertEqual(headers["location"], str(resuri))
        # Delete resource
        (status, reason, headers, data) = self.rosrs.doRequest(resuri,
            method="DELETE")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No Content")
        # Check that resource is no longer available
        (status, reason, headers, data) = self.rosrs.getROResource(resuri)
        self.assertEqual(status, 404)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testAggregateResourceExt(self):
        # Clean up from past runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        externaluri = rdflib.URIRef("http://example.com/external/resource.txt")
        # Read manifest and check aggregated resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertNotIn((rouri, ORE.aggregates, externaluri), manifest)
        # Aggegate external resource: POST proxy ...
        proxydata = ("""
            <rdf:RDF
              xmlns:ore="http://www.openarchives.org/ore/terms/"
              xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" >
              <ore:Proxy>
                <ore:proxyFor rdf:resource="%s" />
              </ore:Proxy>
            </rdf:RDF>
            """)%externaluri
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy",
            body=proxydata)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        resuri   = links[str(ORE.proxyFor)]
        self.assertEqual(str(resuri),str(externaluri))
        # Read manifest and check aggregated resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertIn((rouri, ORE.aggregates, externaluri), manifest)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testDeleteResourceExt(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create test resource
        externaluri = rdflib.URIRef("http://example.com/external/resource.txt")
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceExt(
            rouri, externaluri)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(resuri, externaluri)
        # Find proxy for resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        query = (
            "SELECT ?p WHERE "
              "{ ?p <%(proxyin)s> <%(rouri)s> ; <%(proxyfor)s> <%(resuri)s> }"%
            { "proxyin":  ORE.proxyIn
            , "proxyfor": ORE.proxyFor
            , "rouri":    str(rouri)
            , "resuri":   str(resuri)
            })
        resp  = manifest.query(query)
        proxyterms = [ b["p"] for b in resp.bindings ]
        self.assertEqual(len(proxyterms), 1)
        proxyuri = proxyterms[0]
        self.assertIsInstance(proxyuri, rdflib.URIRef)
        (status, reason, proxyuri, manifest) = self.rosrs.getROResourceProxy(
            resuri, rouri)
        self.assertEqual(status, 200)
        self.assertIsInstance(proxyuri, rdflib.URIRef)
        # Delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(proxyuri,
            method="DELETE")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No Content")
        # Check that resource is no longer available
        (status, reason, proxyuri, manifest) = self.rosrs.getROResourceProxy(
            resuri, rouri)
        self.assertEqual(status, 200)
        self.assertIsNone(proxyuri)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testGetROResource(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/path", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Get resource content
        (status, reason, headers, data)= self.rosrs.getROResource(
            "test/path", rouri=rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "text/plain")
        self.assertEqual(data, rescontent)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testGetROResourceRDF(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            >
              <rdf:Description rdf:about="http://example.org/file1.txt">
                <dct:title>Title for file1.txt</dct:title>
              </rdf:Description>
            </rdf:RDF>
            """
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file1.rdf", ctype="application/rdf+xml", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Get resource content
        (status, reason, headers, graph)= self.rosrs.getROResourceRDF(
            "test/file1.rdf", rouri=rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        s = rdflib.URIRef("http://example.org/file1.txt")
        self.assertIn((s, DCTERMS.title, rdflib.Literal("Title for file1.txt")), graph)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testGetROResourceProxy(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAggregateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/path", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Get resource proxy
        (status, reason, getproxyuri, manifest) = self.rosrs.getROResourceProxy(
            "test/path", rouri=rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(getproxyuri, proxyuri)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testCreateROAnnotationInt(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file.txt", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create internal annotation
        # createROAnnotationInt(self, rouri, resuri, anngr)
        # return (status, reason, annuri, bodyuri)
        #
        # Create annotation body
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:title>Title for test/file.txt</dct:title>
                <rdfs:seeAlso rdf:resource="http://example.org/test" />
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, bodyproxyuri, bodyuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/ann_file.rdf",
            ctype="application/rdf+xml",
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(str(bodyuri),str(rouri)+"test/ann_file.rdf")
        # Create annotation
        #
        # NOTE: POSTing to RO, so relative references should be relative to RO?
        #       http://tools.ietf.org/html/rfc3986#section-5
        #       But also: http://www.imc.org/atom-syntax/mail-archive/msg07930.html
        #
        # Using explicit xml:base, as that seems to be the way atompub went.
        #
        annotation = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="test/file.txt" />
                 <ao:body rdf:resource="test/ann_file.rdf" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(abodyuri,bodyuri)
        # Create another annotation (shortcut sequence)
        reqheaders = {
            "Link": '''<%s>; rel="%s"'''%(str(resuri), str(AO.annotatesResource) ),
            "Slug": "test/ann_file2.rdf"
            }
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:creator>Creator for test/file.txt</dct:creator>
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/rdf+xml", reqheaders=reqheaders,
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(str(abodyuri),str(rouri)+"test/ann_file2.rdf")
        (status, reason, headers, agraph2) = self.rosrs.doRequestRDF(abodyuri,
            method="GET")
        self.assertIn((resuri, DCTERMS.creator, rdflib.Literal("Creator for test/file.txt")), agraph2)
        # Retrieve annotation
        #
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        manifesturi = rdflib.URIRef(headers["location"])
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations of test/file.txt (resuri)
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        log.debug("- auris "+repr(list(auris)))
        agraph = rdflib.graph.Graph()
        for a in auris:
            buri = manifest.value(subject=a, predicate=AO.body)
            log.debug("- buri "+str(buri))
            agraph.parse(buri)
            log.debug("- agraph:\n"+agraph.serialize(format='xml'))
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertIn((resuri, DCTERMS.title,   rdflib.Literal("Title for test/file.txt")),    agraph)
        self.assertIn((resuri, DCTERMS.creator, rdflib.Literal("Creator for test/file.txt")),  agraph)
        self.assertIn((resuri, RDFS.seeAlso,    rdflib.URIRef("http://example.org/test")), agraph)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    def testCreateROAnnotationIntShortCutOnly(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file.txt", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create annotation (shortcut sequence)
        reqheaders = {
            "Link": '''<%s>; rel="%s"'''%(str(resuri), str(AO.annotatesResource) ),
            "Slug": "test/ann_file2.rdf"
            }
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:creator>Creator for test/file.txt</dct:creator>
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/rdf+xml", reqheaders=reqheaders,
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(str(abodyuri),str(rouri)+"test/ann_file2.rdf")
        (status, reason, headers, agraph2) = self.rosrs.doRequestRDF(abodyuri,
            method="GET")
        self.assertIn((resuri, DCTERMS.creator, rdflib.Literal("Creator for test/file.txt")), agraph2)
        # Retrieve annotation
        #
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        manifesturi = rdflib.URIRef(headers["location"])
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations of test/file.txt (resuri)
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        log.debug("- auris "+repr(list(auris)))
        agraph = rdflib.graph.Graph()
        for a in auris:
            buri = manifest.value(subject=a, predicate=AO.body)
            log.debug("- buri "+str(buri))
            agraph.parse(buri)
            log.debug("- agraph:\n"+agraph.serialize(format='xml'))
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertIn((resuri, DCTERMS.creator, rdflib.Literal("Creator for test/file.txt")),  agraph)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    def testCreateROAnnotationIntNoSlug(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file.txt", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create annotation body
        # (By not supplying a Slug: for the ORE proxy creation, ROSRS should allocate a
        # unique URI for the proxied resource and return that in a Link: header.
        # - per discussion with Piotr on 2012-09-06.)
        proxydata = ("""
            <rdf:RDF
              xmlns:ore="http://www.openarchives.org/ore/terms/"
              xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" >
              <ore:Proxy>
              </ore:Proxy>
            </rdf:RDF>
            """)
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy",
            body=proxydata)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.parseLinks(headers)
        if str(ORE.proxyFor) not in links:
            raise self.error("No ore:proxyFor link in create proxy response",
                            "Proxy URI %s"%str(proxyuri))
        annbodyuri   = rdflib.URIRef(links[str(ORE.proxyFor)])
        # PUT annotation body content to indicated URI
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:title>Title for test/file.txt</dct:title>
                <rdfs:seeAlso rdf:resource="http://example.org/test" />
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.doRequest(annbodyuri,
            method="PUT", ctype="application/rdf+xml", body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create annotation itself
        annotation = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="test/file.txt" />
                 <ao:body rdf:resource="%s" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri), str(annbodyuri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(abodyuri,annbodyuri)
        # Retrieve annotation
        #
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        manifesturi = rdflib.URIRef(headers["location"])
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations of test/file.txt (resuri)
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        log.debug("- auris "+repr(list(auris)))
        agraph = rdflib.graph.Graph()
        for a in auris:
            buri = manifest.value(subject=a, predicate=AO.body)
            log.debug("- buri "+str(buri))
            agraph.parse(buri)
            log.debug("- agraph:\n"+agraph.serialize(format='xml'))
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertIn((resuri, DCTERMS.title,   rdflib.Literal("Title for test/file.txt")),    agraph)
        self.assertIn((resuri, RDFS.seeAlso,    rdflib.URIRef("http://example.org/test")), agraph)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    def testCreateROAnnotationExt(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create external test resource
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceExt(
            rouri, rdflib.URIRef("http://example.org/ext"))
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(resuri, rdflib.URIRef("http://example.org/ext"))
        # Create external annotation
        # def createROAnnotationExt(self, rouri, resuri, bodyuri):
        #     assert False, "@@TODO"
        #     return (status, reason, annuri)
        #
        # Create annotation
        annotation = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="http://example.org/ext" />
                 <ao:body rdf:resource="http://example.org/ext/ann_example1.rdf" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(abodyuri, rdflib.URIRef("http://example.org/ext/ann_example1.rdf"))
        # Retrieve annotation
        #
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See Other")
        manifesturi = rdflib.URIRef(headers["location"])
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations of test/file.txt (resuri)
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        buris = [ manifest.value(subject=auri, predicate=AO.body) for auri in auris ]
        self.assertIn(abodyuri, buris)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    #@unittest.skip("Awaiting fix for RODL update annotation")
    def testUpdateROAnnotationInt(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file.txt", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create annotation body
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:title>Title 1</dct:title>
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, bodyproxyuri, bodyuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/ann_file1.rdf",
            ctype="application/rdf+xml",
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(str(bodyuri),str(rouri)+"test/ann_file1.rdf")
        # Create annotation
        annotation1 = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="test/file.txt" />
                 <ao:body rdf:resource="test/ann_file1.rdf" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation1)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(abodyuri,bodyuri)
        # Create new annotation body
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:title>Title 2</dct:title>
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, bodyproxyuri, bodyuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/ann_file2.rdf",
            ctype="application/rdf+xml",
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(str(bodyuri),str(rouri)+"test/ann_file2.rdf")
        # Update the annotation
        annotation2 = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="test/file.txt" />
                 <ao:body rdf:resource="test/ann_file2.rdf" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(annuri,
            method="PUT",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation2)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        agraph = rdflib.graph.Graph()
        for auri in auris:
            buri = manifest.value(subject=auri, predicate=AO.body)
            log.debug("- auri: %s, buri %s"%(str(auri), str(buri)))
            agraph.parse(buri)
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertIn((resuri, DCTERMS.title, rdflib.Literal("Title 2")), agraph)
        self.assertNotIn((resuri, DCTERMS.title, rdflib.Literal("Title 1")), agraph)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    def testRemoveROAnnotation(self):
        # Clean up from previous runs
        self.rosrs.deleteRO("TestAnnotateRO/")
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAnnotateRO",
            "Test RO for annotating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create internal test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/file.txt", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        # Create annotation body
        annbody = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:dct="http://purl.org/dc/terms/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
              <rdf:Description rdf:about="test/file.txt">
                <dct:title>Title 1</dct:title>
              </rdf:Description>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, bodyproxyuri, bodyuri) = self.rosrs.aggregateResourceInt(
            rouri, "test/ann_file1.rdf",
            ctype="application/rdf+xml",
            body=annbody)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(str(bodyuri),str(rouri)+"test/ann_file1.rdf")
        # Create annotation
        annotation1 = """<?xml version="1.0" encoding="UTF-8"?>
            <rdf:RDF
               xmlns:ro="http://purl.org/wf4ever/ro#"
               xmlns:ao="http://purl.org/ao/"
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
               xml:base="%s"
            >
               <ro:AggregatedAnnotation>
                 <ao:annotatesResource rdf:resource="test/file.txt" />
                 <ao:body rdf:resource="test/ann_file1.rdf" />
               </ro:AggregatedAnnotation>
            </rdf:RDF>
            """%(str(rouri))
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST",
            ctype="application/vnd.wf4ever.annotation",
            body=annotation1)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        annuri   = rdflib.URIRef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        aresuri  = links[str(AO.annotatesResource)]
        abodyuri = links[str(AO.body)]
        self.assertEqual(aresuri,resuri)
        self.assertEqual(abodyuri,bodyuri)
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        agraph = rdflib.graph.Graph()
        for auri in auris:
            buri = manifest.value(subject=auri, predicate=AO.body)
            log.debug("- auri: %s, buri %s"%(str(auri), str(buri)))
            agraph.parse(buri)
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertIn((resuri, DCTERMS.title, rdflib.Literal("Title 1")), agraph)
        # Remove the annotation
        (status, reason, headers, data) = self.rosrs.doRequest(annuri,
            method="DELETE")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No Content")
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Scan the manifest for annotations
        auris = [ a for (a,p) in manifest.subject_predicates(object=resuri)
                    if p in [AO.annotatesResource,RO.annotatesAggregatedResource] ]
        agraph = rdflib.graph.Graph()
        for auri in auris:
            buri = manifest.value(subject=auri, predicate=AO.body)
            log.debug("- auri: %s, buri %s"%(str(auri), str(buri)))
            agraph.parse(buri)
        log.debug("- final agraph:\n"+agraph.serialize(format='xml'))
        self.assertNotIn((resuri, DCTERMS.title, rdflib.Literal("Title 1")), agraph)
        # Clean up
        self.rosrs.deleteRO("TestAnnotateRO/")
        return

    #@@TODO move these to separate test suite

    def testCopyRO(self):
        return

    def testCancelCopyRO(self):
        return

    def testUpdateROStatus(self):
        return

    def testGetROEvolution(self):
        return

    # Sentinel/placeholder tests

    def testUnits(self):
        assert (True)

    def testComponents(self):
        assert (True)

    def testIntegration(self):
        assert (True)

    def testPending(self):
        assert (False), "Pending tests follow"

# Assemble test suite

def getTestSuite(select="unit"):
    """
    Get test suite

    select  is one of the following:
            "unit"      return suite of unit tests only
            "component" return suite of unit and component tests
            "all"       return suite of unit, component and integration tests
            "pending"   return suite of pending tests
            name        a single named test to be run
    """
    testdict = {
        "unit":
            [ "testUnits"
            , "testListROs"
            , "testCreateRO"
            , "testDeleteRO"
            , "testGetROManifest"
            , "testGetROPage"
            , "testGetROZip"
            , "testAggregateResourceIntFull"
            , "testAggregateResourceIntShort"
            , "testDeleteResourceInt"
            , "testAggregateResourceExt"
            , "testDeleteResourceExt"
            , "testGetROResource"
            , "testGetROResourceRDF"
            , "testGetROResourceProxy"
            , "testCreateROAnnotationInt"
            , "testCreateROAnnotationIntShortCutOnly"
            , "testCreateROAnnotationIntNoSlug"
            , "testCreateROAnnotationExt"
            , "testUpdateROAnnotationInt"
            , "testRemoveROAnnotation"
            #@@TODO move these to separate test suite
            #, "testCopyRO"
            #, "testCancelCopyRO"
            #, "testUpdateROStatus"
            #, "testGetROEvolution"
            ],
        "component":
            [ "testComponents"
            ],
        "integration":
            [ "testIntegration"
            ],
        "pending":
            [ "testPending"
            ]
        }
    return TestUtils.getTestSuite(TestApi_ROSRS, testdict, select=select)

if __name__ == "__main__":
    TestUtils.runTests("TestApi_ROSRS.log", getTestSuite, sys.argv)

# End.
