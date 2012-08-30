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

from ro_namespaces import RDF, ORE, RO, DCTERMS
from ROSRS_Session import ROSRS_Error, ROSRS_Session

# Logging object
log = logging.getLogger(__name__)

# Base directory for file access tests in this module
testbase = os.path.dirname(__file__)

# Test config details

class Config:
    ROSRS_API_URI = "http://sandbox.wf4ever-project.org/rodl/ROs/"
    AUTHORIZATION = "47d5423c-b507-4e1c-8"

# Class for ROSRS errors

# @@TODO delete class
class ROSRS_ErrorZZZ(Exception):

    def __init__(self, msg="ROSRS_Error", value=None, srsuri=None):
        self._msg    = msg
        self._value  = value
        self._srsuri = srsuri
        return

    def __str__(self):
        txt = self._msg
        if self._srsuri: txt += " for "+str(self._srsuri)
        if self._value:  txt += ": "+repr(self._value)
        return txt

    def __repr__(self):
        return ( "ROSRS_Error(%s, value=%s, srsuri=%s)"%
                 (repr(self._msg), repr(self._value), repr(self._srsuri)))

# Class for handling ROSRS access

# @@TODO delete class
class ROSRS_SessionZZZ(object):
    
    """
    Client access class for RO SRS - creates a session to access a single ROSRS endpoint,
    and provides methods to access ROs and RO resources via the RO SRS API.
    
    See:
    * http://www.wf4ever-project.org/wiki/display/docs/RO+SRS+interface+6
    * http://www.wf4ever-project.org/wiki/display/docs/RO+evolution+API
    
    Related:
    * http://www.wf4ever-project.org/wiki/display/docs/User+Management+2
    """

    def __init__(self, srsuri, accesskey):
        log.debug("ROSRS_Session.__init__: srsuri "+srsuri)
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

    def error(self, msg, value=None):
        return ROSRS_Error(msg=msg, value=value, srsuri=self._srsuri)

    def parseLinks(self, headers):
        """
        Parse link header(s), return dictionary of links keyed by link relation type
        """
        linkvallist = [ v for (h,v) in headers["_headerlist"] if h == "link" ]
        log.debug("parseLinks linkvallist %s"%(repr(linkvallist)))
        links = {}
        for linkval in linkvallist:
            # <http://sandbox.wf4ever-project.org/rodl/ROs/TestAggregateRO/test/path>; rel=http://www.openarchives.org/ore/terms/proxyFor
            # @@TODO: This regex might be fragile if more Link parameters are present
            linkmatch = re.match(r'''\s*<([^>]*)>\s*;\s*rel\s*=\s*"?([^"]*)"?''', linkval)
            if linkmatch:
                log.debug("parseLinks [%s] = %s"%(linkmatch.group(2), linkmatch.group(1)))
                links[linkmatch.group(2)] = rdflib.URIRef(linkmatch.group(1))
        return links

    def doRequest(self, uripath, method="GET", body=None, ctype=None, accept=None, reqheaders=None):
        """
        Perform HTTP request to ROSRS
        Return status, reason(text), response headers, response body
        """
        # Sort out path to use in HTTP request: request may be path or full URI or rdflib.URIRef
        uripath = str(uripath)        # get URI string from rdflib.URIRef
        log.debug("ROSRS_Session.doRequest uripath:  "+str(uripath))
        uriparts = urlparse.urlsplit(urlparse.urljoin(self._srspath,uripath))
        log.debug("ROSRS_Session.doRequest uriparts: "+str(uriparts))
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
        log.debug("ROSRS_Session.doRequest method:     "+method)
        log.debug("ROSRS_Session.doRequest path:       "+path)
        log.debug("ROSRS_Session.doRequest reqheaders: "+repr(reqheaders))
        log.debug("ROSRS_Session.doRequest body:       "+repr(body))
        self._httpcon.request(method, path, body, reqheaders)
        # Pick out elements of response
        response = self._httpcon.getresponse()
        status   = response.status
        reason   = response.reason
        headerlist = [ (h.lower(),v) for (h,v) in response.getheaders() ]
        headers  = dict(headerlist)   # dict(...) keeps last result of multiple keys
        headers["_headerlist"] = headerlist
        data = response.read()
        log.debug("ROSRS_Session.doRequest response: "+str(status)+" "+reason)
        log.debug("ROSRS_Session.doRequest headers:  "+repr(headers))
        log.debug("ROSRS_Session.doRequest data:     "+repr(data))
        return (status, reason, headers, data)

    def doRequestRDF(self, uripath, method="GET", body=None, ctype=None, reqheaders=None):
        """
        Perform HTTP request with RDF response.
        If requests succeeds, return response as RDF graph,
        or return fake 9xx status if RDF cannot be parsed
        otherwise return responbse and content per request.
        Thus, only 2xx responses include RDF data.
        """
        (status, reason, headers, data) = self.doRequest(uripath,
            method=method, body=body,
            ctype=ctype, accept="application/rdf+xml", reqheaders=reqheaders)
        if status >= 200 and status < 300:
            if headers["content-type"].lower() == "application/rdf+xml":
                rdfgraph = rdflib.graph.Graph()
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
            raise self.error("Error listing ROs", "%03d %s"%(status, reason))
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
            "title":    title,
            "creator":  creator,
            "date":     date
            }
        roinfotext = json.dumps(roinfo)
        (status, reason, headers, data) = self.doRequestRDF("",
            method="POST", body=roinfotext, reqheaders=reqheaders)
        log.debug("ROSRS_session.createRO: %03d %s: %s"%(status, reason, repr(data)))
        if status == 201:
            return (status, reason, rdflib.URIRef(headers["location"]), data)
        if status == 409:
            return (status, reason, None, data)
        #@@TODO: Create annotations for title, creator, date??
        raise self.error("Error creating RO", "%03d %s"%(status, reason))

    def deleteRO(self, rouri):
        """
        Delete an RO
        Return (status, reason), where status is 204 or 404
        """
        (status, reason, headers, data) = self.doRequest(rouri,
            method="DELETE",
            accept="application/rdf+xml")
        if status in [204, 404]:
            return (status, reason)
        raise self.error("Error deleting RO", "%03d %s"%(status, reason))

    def getROResource(self, resuriref, rouri=None, accept=None, reqheaders=None):
        """
        Retrieve resource from RO
        Return (status, reason, headers, data), where status is 200 or 404
        """
        resuri = str(resuriref)
        if rouri:
            resuri = urlparse.urljoin(str(rouri), resuri)
        (status, reason, headers, data) = self.doRequest(resuri,
            method="GET", accept=accept, reqheaders=reqheaders)
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO resource", "%03d %s (%s)"%(status, reason, resuriref))

    def getROResourceRDF(self, resuriref, rouri=None, reqheaders=None):
        """
        Retrieve RDF resource from RO
        Return (status, reason, headers, data), where status is 200 or 404
        """
        resuri = str(resuriref)
        if rouri:
            resuri = urlparse.urljoin(str(rouri), resuri)
        (status, reason, headers, data) = self.doRequestRDF(resuri,
            method="GET", reqheaders=reqheaders)
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO resource", "%03d %s (%s)"%(status, reason, resuriref))

    def getROResourceProxy(self, resuriref, rouri):
        """
        Retrieve proxy description for resource.
        Return (proxyuri, manifest)
        """
        (status, reason, headers, manifest) = self.getROManifest(rouri)
        if status != 200:
            raise self.error("Error retrieving RO manifest", "%d03 %s"%
                             (status, reason))
        resuri = rdflib.URIRef(urlparse.urljoin(str(rouri), str(resuriref)))
        proxyterms = list(manifest.subjects(predicate=ORE.proxyFor, object=resuri))
        log.debug("getROResourceProxy proxyterms: %s"%(repr(proxyterms)))
        proxyuri = None
        if len(proxyterms) == 1:
            proxyuri = proxyterms[0]
        return (proxyuri, manifest)

    def getROManifest(self, rouri):
        """
        Retrieve an RO manifest
        Return (status, reason, headers, data), where status is 200 or 404
        """
        (status, reason, headers, data) = self.doRequestRDF(rouri,
            method="GET")
        if status == 303:
            uri = headers["location"]
            (status, reason, headers, data) = self.doRequestRDF(uri,
                method="GET")
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO manifest",
            "%d03 %s"%(status, reason))

    # def getROLandingPage(self, rouri):

    def getROZip(self, rouri):
        """
        Retrieve an RO as ZIP file
        Return (status, reason, headers, data), where status is 200 or 404
        """
        (status, reason, headers, data) = self.doRequest(rouri,
            method="GET", accept="application/zip")
        if status == 303:
            uri = headers["location"]
            (status, reason, headers, data) = self.doRequest(uri,
                method="GET", accept="application/zip")
        if status in [200, 404]:
            return (status, reason, headers, data if status == 200 else None)
        raise self.error("Error retrieving RO as ZIP file",
            "%d03 %s"%(status, reason))

    def aggregateResourceInt(
            self, rouri, respath, ctype="application/octet-stream", body=None):
        """
        Aggegate internal resource
        Return (status, reason, proxyuri, resuri), where status is 200 or 201
        """
        # POST (empty) proxy value to RO ...
        reqheaders = { "slug": respath }
        proxydata = ("""
            <rdf:RDF
              xmlns:ore="http://www.openarchives.org/ore/terms/"
              xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" >
              <ore:Proxy>
              </ore:Proxy>
            </rdf:RDF>
            """)
        (status, reason, headers, data) = self.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy",
            reqheaders=reqheaders, body=proxydata)
        if status != 201:
            raise self.error("Error creating aggregation proxy",
                            "%d03 %s (%s)"%(status, reason, respath))
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.parseLinks(headers)
        if str(ORE.proxyFor) not in links:
            raise self.error("No ore:proxyFor link in create proxy response",
                            "Proxy URI %s"%str(proxyuri))
        resuri   = rdflib.URIRef(links[str(ORE.proxyFor)])
        # PUT resource content to indicated URI
        (status, reason, headers, data) = self.doRequest(resuri,
            method="PUT", ctype=ctype, body=body)
        if status not in [200,201]:
            raise self.error("Error creating aggregated resource content",
                "%d03 %s (%s)"%(status, reason, respath))
        return (status, reason, proxyuri, resuri)

    def aggregateResourceExt(self, rouri, resuri):
        """
        Aggegate extternal resource
        Return (status, reason, proxyuri, resuri), where status is 200 or 201
        """
        # Aggegate external resource: POST proxy ...
        proxydata = ("""
            <rdf:RDF
              xmlns:ore="http://www.openarchives.org/ore/terms/"
              xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" >
              <ore:Proxy>
                <ore:proxyFor rdf:resource="%s" />
              </ore:Proxy>
            </rdf:RDF>
            """)%str(resuri)
        (status, reason, headers, data) = self.doRequest(rouri,
            method="POST", ctype="application/vnd.wf4ever.proxy",
            body=proxydata)
        if status != 201:
            raise self.error("Error creating aggregation proxy",
                "%d03 %s (%s)"%(status, reason, str(resuri)))
        proxyuri = rdflib.URIRef(headers["location"])
        links    = self.parseLinks(headers)
        return (status, reason, proxyuri, rdflib.URIRef(resuri))

    def removeResource(self, rouri, resuri):
        """
        Remove resource from aggregation (internal or external)
        return (status, reason), where status is 204 No content or 404 Not found
        """
        # Find proxy for resource
        (proxyuri, manifest) = self.getROResourceProxy(resuri, rouri)
        if proxyuri == None: return (404, "Not Found")
        assert isinstance(proxyuri, rdflib.URIRef)
        # Delete proxy
        (status, reason, headers, data) = self.doRequest(proxyuri,
            method="DELETE")
        if status == 307:
            # Redirect to internal resource: delete that
            assert headers["location"] == str(resuri)
            (status, reason, headers, data) = self.doRequest(resuri,
                method="DELETE")
        log.debug("removeResource %s from %s: status %d, reason %s"%
                  (str(resuri), str(rouri), status, reason))
        assert status == 204
        return (status, reason)

    def createROAnnotationInt(self, rouri, resuri, anngr):
        assert False, "@@TODO"
        return (status, reason, annuri, bodyuri)

    def createROAnnotationExt(self, rouri, resuri, bodyuri):
        assert False, "@@TODO"
        return (status, reason, annuri)

    def updateROAnnotationInt(self, rouri, annuri, bodyuri):
        assert False, "@@TODO"
        return (status, reason, annuri, )

    def getROResourceAnnotations(self, rouri, resuri):
        assert False, "@@TODO"
        yield annuri

    def getROAnnotation(self, annuri):
        assert False, "@@TODO"
        return (status, reason, anngr)

    def removeROAnnotation(self, rouri, annuri):
        assert False, "@@TODO"
        return (status, reason)

    # See: http://www.wf4ever-project.org/wiki/display/docs/RO+evolution+API

    # Need to fugure out how deferred values can work, associated with copyuri
    # e.g. poll, notification subscribe, sync options

    def copyRO(self, oldrouri, slug):
        assert False, "@@TODO"
        return (status, reason, copyuri)
        # copyuri ->  Deferred(oldrouri, rotype, rostatus, newrouri)

    def cancelCopyRO(self, copyuri):
        assert False, "@@TODO"
        return (status, reason)

    def updateROStatus(self, rouri, rostatus):
        assert False, "@@TODO"
        return (status, reason, updateuri)

    def getROEvolution(self, rouri):
        assert False, "@@TODO"
        return (status, reason, evogr)


# ------------------------------------------------------------------------

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
        (proxyuri, manifest) = self.rosrs.getROResourceProxy(resuri, rouri)
        self.assertIsInstance(proxyuri, rdflib.URIRef)
        # Delete proxy
        (status, reason, headers, data) = self.rosrs.doRequest(proxyuri,
            method="DELETE")
        self.assertEqual(status, 204)
        self.assertEqual(reason, "No Content")
        # Check that resource is no longer available
        (proxyuri, manifest) = self.rosrs.getROResourceProxy(resuri, rouri)
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
        log.debug("testDeleteResourceInt proxyuri: %s"%str(proxyuri))
        log.debug("testDeleteResourceInt   resuri: %s"%str(resuri))
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
        log.debug("testDeleteResourceInt proxyuri: %s"%str(proxyuri))
        log.debug("testDeleteResourceInt   resuri: %s"%str(resuri))
        # Get resource proxy
        (getproxyuri, manifest)= self.rosrs.getROResourceProxy(
            "test/path", rouri=rouri)
        self.assertEqual(getproxyuri, proxyuri)
        # Clean up
        self.rosrs.deleteRO("TestAggregateRO/")
        return

    def testCreateROAnnotationInt(self):
        return

    def testCreateROAnnotationExt(self):
        return

    def testGetROResourceAnnotations(self):
        return

    def testGetROAnnotation(self):
        return

    def testUpdateROAnnotationInt(self):
        return

    def testRemoveROAnnotation(self):
        return

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
            , "testGetROResourceProxy"
            , "testCreateROAnnotationInt"
            , "testCreateROAnnotationExt"
            , "testGetROResourceAnnotations"
            , "testGetROAnnotation"
            , "testUpdateROAnnotationInt"
            , "testRemoveROAnnotation"
            , "testCopyRO"
            , "testCancelCopyRO"
            , "testUpdateROStatus"
            , "testGetROEvolution"
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
