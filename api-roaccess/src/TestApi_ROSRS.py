#!/usr/bin/env python

"""
Module to test RO SRS APIfunctions
"""

import os, os.path
import sys
import unittest
import logging
import json
import StringIO
import httplib
#import urllib
import urlparse
import rdflib

from MiscLib import TestUtils

# Logging object
log = logging.getLogger(__name__)

# Base directory for file access tests in this module
testbase = os.path.dirname(__file__)

# Class for ROSRS errors

class ROSRS_Error(Exception):

    def __init__(self, msg="ROSRS_Error", value=None, srsuri=None):
        self._msg    = msg
        self._value  = value
        self._srsuri = srsuri
        return

    def __str__(self):
        str = self._msg
        if self._srsuri: str += " for "+self._srsuri
        if self._value:  str += ": "+repr(value)
        return str

    def __repr__(self):
        return ( "ROSRS_Error(%s, value=%s, srsuri=%s)"%
                 (repr(self._msg), repr(self._value), repr(self._srsuri)))

# Class for handling ROSRS access

class ROSRS_Session(object):

    def __init__(self, srsuri, accesskey):
        self._srsuri    = srsuri
        self._key       = accesskey
        parseduri       = urlparse.urlsplit(srsuri)
        self._srsscheme = parseduri.scheme
        self._srshost   = parseduri.netloc
        self._srspath   = parseduri.path
        self._httpcon   = httplib.HTTPConnection(self._srshost)
        return

    def close(self):
        self._key = None
        self._httpcon.close()
        return

    def baseuri(self):
        return self._srsuri

    def error(self, msg, value):
        return ROSRS_Error(msg=msg, value=value, srsuri=self._srsuri)

    def parseLinks(headers):
        """
        Parse link header(s), return dictionary of links keyed by link relation type
        """
        linkvallist = [ v for (h,v) in headers["_headerlist"] if h == "link" ]
        links = {}
        for linkval in linkvallist:
            linkmatch = re.match(r'''\s*<([^>]*)>\s*;\s*rel\s*=\s*"([^"]*)"''', linkval)
            if linkmatch:
                links[linkmatch.group(2)] = rdflib.URIRef(linkmatch.group(1))
        return links

    def doRequest(self, uripath, method="GET", body=None, ctype=None, accept=None, reqheaders=None):
        """
        Perform HTTP request to ROSRS
        Return status, reason(text), response headers, response body
        """
        # Sort out path to use in HTTP request: request may be path or full URI or rdflib.URIRef
        uripath = str(uripath)        # get URI string from rdflib.URIRef
        uriparts = urlparse.urlsplit(urlparse.urljoin(self._srspath,uripath))
        if uriparts.scheme:
            if self._srsscheme != uriparts.scheme:
                raise ROSRS_Error(
                    "ROSRS URI scheme mismatch",
                    value=uriparts.scheme,
                    srsuri=self._srsuri)
        if uriparts.netloc:
            if self._srshost != uriparts.netloc:
                raise ROSRS_Error(
                    "ROSRS URI host:port mismatch",
                    value=uriparts.netloc,
                    srsuri=self._srsuri)
        path = uriparts.path
        if uriparts.query: path += "?"+uriparts.query
        # Assemble request headers
        if not reqheaders:
            reqheaders = {}
        reqheaders["authorization"] = "Bearer "+self._key
        if ctype:
            reqheaders["content-type"] = ctype
        if accept:
            reqheaders["accept"] = accept
        # Execute request
        self._httpcon.request(method, path, body, reqheaders)
        # Pick out elements of response
        response = self._httpcon.getresponse()
        status   = response.status
        reason   = response.reason
        headerlist = [ (h.lower(),v)) for (h,v) in response.getheaders() ]
        headers  = dict(headerlist)   # dict(...) keeps last result of multiple keys
        headers["_headerlist"] = headerlist
        data = response.read()
        return (status, reason, headers, data)

    def doRequestRDF(self, uripath, method="GET", body=None, ctype=None, headers=None):
        """
        Perform HTTP request with RDF response.
        If requests succeeds, return response as RDF graph,
        or return fake 9xx status if RDF cannot be parsed
        otherwise return responbse and content per request.
        Thus, only 2xx responses include RDF data.
        """
        (status, reason, headers, data) = self.rosrs.doRequest(uripath,
            method=method, body=body,
            ctype=ctype, accept="application/rdf+xml", headers=headers)
        if status >= 200 and status < 300:
            if headers["content-type"].lower() == "application/rdf+xml":
                rdfgraph = rdflib.Graph()
                try:
                    rdfgraph.parse(data=data, format="xml")
                    data = rdfgraph
                except Exception, e:
                    status   = 902
                    reason   = "RDF parse failure"
            else:
                status   = 901
                reason   = "Non-RDF content-type returned"
        return (status, reason, headers, data)

    def listROs(self):
        """
        List ROs in service

        Result is list of dictionaries, where dict["uri"] is the URI of an RO.
        """
        (status, reason, headers, data) = self.doRequest("")
        if status < 200 or status >= 300:
            raise self.error("Error listing ROs", "%d03 %s"%(status, reason))
        log.debug("ROSRS_session.listROs: %s"%(repr(data)))
        urilist = data.splitlines()
        return [ { "uri" : u } for u in urilist ]

    def createRO(self, id, title, creator, date):
        """
        Create a new RO, return (status, reason, uri, manifest):
        status+reason: 201 Created or 409 Exists
        uri+manifest: URI and copy of manifest as RDF graph if 201 status,
                      otherwise None and response data as diagnostic
        """
        reqheaders   = {
            "slug":     id
            }
        roinfo = {
            "id":       id,
            "title":    title
            "creator":  creator
            "date":     date
            }
        roinfotext = json.dumps(roinfo)
        (status, reason, headers, data) = self.rosrs.doRequestRDF("",
            method="POST", body=roinfotext, headers=reqheaders)
        log.debug("ROSRS_session.createRO: %d03 %s: %s"%(status, reason, repr(data)))
        if status == 201:
            return (status, reason, rdflib.URIRef(headers["location"]), data)
        if status == 409:
            return (status, reason, None, data)
        raise self.error("Error creating RO", "%d03 %s"%(status, reason))

    def deleteRO(self, rouri):
        """
        Delete an RO
        """
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="DELETE",
            accept="application/rdf+xml")
        if status in [204, 404]:
            return (status, reason)
        raise self.error("Error deleting RO", "%d03 %s"%(status, reason))

    def getROManifest(self, rouri):
        """
        Retrieve an RO manifest
        """
        (status, reason, headers, data) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        if status == 303:
            uri = headers["location"]
            (status, reason, headers, data) = self.rosrs.doRequestRDF(uri,
                method="GET")
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO manifest", "%d03 %s"%(status, reason))

    def getROResource(self, resuriref, rouri=None, accept=None, reqheaders=None):
        """
        Retrieve resource from RO
        """
        if rouri:
            resuri = urlparse.urljoin(rouri, resuriref)
        else:
            resuri = resuriref
        (status, reason, headers, data) = self.doRequest(resuri,
            method="GET", accept=accept, reqheaders=reqheaders)
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO manifest", "%d03 %s"%(status, reason))

    def aggregateResourceInt(rouri, ctype="application/octet-stream", body=None):
        # @@TODO: create internal resource - use code from long-form test case when passes
        return (status, reason, proxyuri, resuri)


# Test cases

class TestApi_ROSRS(unittest.TestCase):

    def setUp(self):
        super(TestApi_ROSRS, self).setUp()
        # @@TODO - use separate config for this
        self.rosrs = ROSRS_Session("http://sandbox.wf4ever.org/RODL/ROs/",
            accesskey="abcdef")
        return

    def tearDown(self):
        super(TestApi_ROSRS, self).tearDown()
        self.rosrs.close()
        return

    # Actual tests follow

    def testListROs(self):
        # Access RO SRS to list ROs: GET to ROSRS
        (status, reason, headers, data) = self.rosrs.doRequest("",
            accept="application/rdf+xml")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        return

    def testCreateRO(self):
        # Create an RO: POST to ROSRS
        reqheaders   = {
            "slug":     "TestCreateRO"
            }
        roinfo = {
            "id":       "TestCreateRO",
            "title":    "Test create research object"
            "creator":  "TestAPI_ROSRS.py"
            "date":     "2012-06-27"
            }
        roinfotext = json.dumps(roinfo)
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF("",
            method="POST", headers=reqheaders, body=roinfotext,
            accept="application/rdf+xml")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        self.assertEqual(headers["location"], self.rosrs.baseuri()+"TestCreateRO/")
        # Check manifest RDF graph
        rouri = rdflib.URIRef(headers["location"])
        self.assertIn((rouri, RDF.type, RO.ResearchObject), manifest)
        # Test that new RO is in collection
        # Response is simple list of URIs (for now)
        rolist = self.rosrs.listROs()
        self.assertEqual(status, 200)
        self.assertIn(str(rouri), [ r["uri"] for r in rolist ] )
        # Clean up
        self.rosrs.deleteRO("TestCreateRO/")
        return

    def testDeleteRO(self):
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestDeleteRO",
            "Test RO for deletion", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Test that new RO is in collection
        rolist = self.rosrs.listROs()
        self.assertEqual(status, 200)
        self.assertIn(self.rosrs.baseuri+"TestDeleteRO/", [ r["uri"] for r in rolist ] )
        # Delete an RO; locate proxy, delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="DELETE",
            accept="application/rdf+xml")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No content")
        # Test that new RO is not in collection
        rolist = self.rosrs.listROs()
        self.assertEqual(status, 200)
        self.assertNotIn(self.rosrs.baseuri+"TestDeleteRO/", [ r["uri"] for r in rolist ] )
        return

    def testGetROManifest(self):
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO manifest
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(rouri,
            method="GET")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See other")
        manifesturi = headers["location"]
        (status, reason, headers, manifest) = self.rosrs.doRequestRDF(manifesturi,
            method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        # Check manifest RDF graph
        self.assertIn((rouri, RDF.type, RO.ResearchObject), manifest)

        # @@ other tests here @@

        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testGetROPage(self):
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO landing page
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="GET", accept="text/html")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See other")
        pageuri = headers["location"]
        (status, reason, headers, data) = self.rosrs.doRequest(pageuri,
            method="GET", accept="text/html")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "text/html")
        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testGetROZip(self):
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestGetRO",
            "Test RO for manifest access", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Access RO content
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="GET", accept="application/zip")
        self.assertEqual(status, 303)
        self.assertEqual(reason, "See other")
        pageuri = headers["location"]
        (status, reason, headers, data) = self.rosrs.doRequest(pageuri,
            method="GET", accept="application/zip")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/zip")
        # @@ test content of zip (data)?
        # Clean up
        self.rosrs.deleteRO("TestGetRO/")
        return

    def testAggregateResourceExt(self):
        # Aggegate external resource: POST proxy
        assert False, "@@TODO - when internal test passes, hack code"
        return

    def testAggregateResourceIntFull(self):
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Aggegate internal resource: POST proxy ...
        (status, reason, headers, data) = self.rosrs.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy")
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        proxyuri = rdflib.URURef(headers["location"])
        links    = self.rosrs.parseLinks(headers)
        resuri   = links[str(ORE.proxyFor)]
        # ... then PUT content
        rescontent = "Resource content\n"
        (status, reason, headers, data) = self.rosrs.doRequest(resuri,
            method="PUT", ctype="text/plain", body=rescontent)
        self.assertEqual(status, 201)
        self.assertEqual(reason, "Created")
        self.assertEqual(headers["location"], str(resuri))
        ####links    = self.rosrs.parseLinks(headers)
        ####self.assertEqual(links[str(ORE.proxy)], str(resuri))
        # Read manifest and check aggregated resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertIn( (rouri, ORE.aggregates, resuri), manifest )
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testAggregateResourceShort(self):
        # Aggegate internal resource (shortcut): POST content
        assert False, "@@TODO - when long-form test passes, hack code"
        return

    def testDeleteResourceExt(self):
        # De-aggregate external resource: find proxy URI, DELETE proxy
        # Create test RO
        (status, reason, rouri, manifest) = self.rosrs.createRO("TestAggregateRO",
            "Test RO for aggregating resourcess", "TestApi_ROSRS.py", "2012-06-29")
        self.assertEqual(status, 201)
        # Create test resource
        rescontent = "Resource content\n"
        (status, reason, proxyuri, resuri) = self.rosrs.aggregateResourceInt(rouri, ctype="text/plain", body=rescontent)
        self.assertEqual(status, 200)
        # Find proxy for resource
        (status, reason, headers, manifest) = self.rosrs.getROManifest(rouri)
        self.assertEqual(status, 200)
        resp = manifest.query("SELECT ?p WHERE { ?p <%(proxyin)s> <%(rouri)s> ; <%(proxyfor)s> <%(resuri)s> .")
        proxyterms = [ b["p"] for b in resp.bindings ]
        self.assertEqual(len(proxyterms), 1)
        proxyuri = proxyterms[0]
        self.assertIsInstancel(proxyuri, rdflib.URIRef)
        # Delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(proxyuri,
            method="DELETE")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No content")
        # Check that resource is no longer available
        (status, reason, headers, data) = self.rosrs.getROResource(uri)
        self.assertEqual(status, 404)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testDeleteResourceInt(self):
        # De-aggregate internal resource: find proxy URI, DELETE proxy, redirect
        # @@ Discussing whether to not do redirect.
        return

    def testCreateAnnotation(self):
        # Assume annotation body URI is known - internal or external
        # POST annotation to RO
        return

    def testDeleteAnnotation(self):
        # Delete an annotation (leaves annotation body):
        # find annotation URI, DELETE annotation
        return

    def testCopyROasNew(self):
        # Copy an existing RO as a new RO (part of RO EVO API)
        # POST description of new RO to ROSR service
        return

    def testUpdateROStatus(self):
        # Update statius of RO (part of RO EVO API)
        # HEAD to locate associated roevo resource, POST to roevo resource
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
            , "testAggregateResourceExt"
            , "testAggregateResourceIntFull"
            , "testAggregateResourceShort"
            , "testDeleteResourceExt"
            , "testDeleteResourceInt"
            , "testCreateAnnotation"
            , "testDeleteAnnotation"
            , "testCopyROasNew"
            , "testUpdateROStatus"
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
