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

    def doRequest(self, uripath, method="GET", body=None, accept=None, reqheaders=None):
        """
        Perform HTTP request to ROSRS
        Return status, reason(text), response headers, response body
        """
        # Sort out path to use in HTTP request: request may be path or full URI
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
        if accept:
            reqheaders["accept"] = accept
        # Execute request
        self._httpcon.request(method, path, body, reqheaders)
        # Pick out elements of response
        response = self._httpcon.getresponse()
        status   = response.status
        reason   = response.reason
        headers  = dict(response.getheaders())  # Keeps last occurrence of multiple headers
        data     = response.read()
        return (status, reason, headers, data)

    def doRequestRDF(self, uripath, method="GET", body=None, headers=None):
        """
        Perform HTTP request with RDF response.
        If requests succeeds, return response as RDF graph,
        or return fake 600 status if RDF cannot be parsed.
        """
        (status, reason, headers, data) = self.rosrs.doRequest(uripath,
            method=method, body=bory,
            accept="application/rdf+xml", headers=headers)
        if status >= 200 and status < 300:
            if headers["content-type"].lower() == "application/rdf+xml":
                rdfgraph = rdflib.Graph()
                try:
                    rdfgraph.parse(data=data, format="xml")
                    data = rdfgraph
                except Exception, e:
                    status   = 600
                    reason   = "RDF parse failure"
            else:
                status   = 600
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
        Create a new RO, return copy of manifest as RDF graph
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
        if status < 200 or status >= 300:
            raise self.error("Error listing ROs", "%d03 %s"%(status, reason))
        log.debug("ROSRS_session.createRO: %d03 %s: %s"%(status, reason, repr(data)))
        return data


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
            "slug":     "TestRO"
            }
        roinfo = {
            "id":       "TestRO",
            "title":    "Test research object"
            "creator":  "TestAPI_ROSRS.py"
            "date":     "2012-06-27"
            }
        roinfotext = json.dumps(roinfo)
        (status, reason, headers, data) = self.rosrs.doRequest("",
            method="POST", headers=reqheaders, body=roinfotext,
            accept="application/rdf+xml")
        self.assertEqual(status, 200)
        self.assertEqual(reason, "OK")
        self.assertEqual(headers["content-type"], "application/rdf+xml")
        self.assertEqual(headers["location"],     "...")
        self.assertEqual(data, [])
        # Test that new RO is in collection
        rolist = self.rosrs.listROs()
        self.assertEqual(status, 200)
        self.assertIn(self.rosrs.baseuri+"TestRO/", [ r["uri"] for r in rolist ] )
        return

    def testDeleteRO(self):
        # Create an RO: POST to ROSRS





        return

    def testGetROManifest(self):
        # Access RO manifest
        return

    def testGetROPage(self):
        # Access RO as landing page
        return

    def testGetROZip(self):
        # Access RO as ZIP file
        return

    def testAggregateResourceExt(self):
        # Aggegate external resource: POST proxy
        return

    def testAggregateResourceIntFull(self):
        # Aggegate internal resource (full form): POST prpxy, then PUT content
        return

    def testAggregateResourceShort(self):
        # Aggegate internal resource (shortcut): POST content
        return

    def testDeleteResourceExt(self):
        # De-aggregate external resource: find proxy URI, DELETE proxy
        return

    def testDeleteResourceInt(self):
        # De-aggregate internal resource: find proxy URI, DELETE proxy, redirect
        return

    def testCreateAnnotation(self):
        # Assume annotation body URI is known - internal or external
        # POST annotation to RO
        return

    def testDeleteAnnotation(self):
        # Delete an annotation (leaves annotation body):
        # find annotation URI, DELETE annotation
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
