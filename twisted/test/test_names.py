
# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


"""
Test cases for twisted.names.
"""
import sys, socket
from pyunit import unittest

from twisted.internet import reactor, protocol, defer
from twisted.names import client, server, common
from twisted.protocols import dns
from twisted.python import log


gotResponse = 0
PORT = 2053

def setDone(message):
    global gotResponse
    gotResponse = 1
    return message

class NoFileAuthority(common.ResolverBase):
    def __init__(self, soa, records):
        common.ResolverBase.__init__(self)
        self.soa, self.records = soa, records

    def _lookup(self, name, cls, type, timeout = 10):
        if name.lower().endswith(self.soa[0].lower()):
            l = [r for r in self.records[name.lower()] if type == dns.ALL_RECORDS or r.TYPE == type]
            for r in l:
                r.ttl = 10
            return defer.succeed(l)
        return defer.fail(dns.DomainError(name))


soa_record = dns.Record_SOA(
                    mname = 'test-domain.com',
                    rname = 'root.test-domain.com',
                    serial = 100,
                    refresh = 1234,
                    minimum = 7654,
                    expire = 19283784,
                    retry = 15
                )

reverse_soa = dns.Record_SOA(
                     mname = '93.84.28.in-addr.arpa',
                     rname = '93.84.28.in-addr.arpa',
                     serial = 120,
                     refresh = 54321,
                     minimum = 382,
                     expire = 11193983,
                     retry = 30
                )

test_domain_com = NoFileAuthority(
    soa = ('test-domain.com', soa_record),
    records = {
        'test-domain.com': [
            dns.Record_A('127.0.0.1'),
            dns.Record_NS('39.28.189.39'),
            dns.Record_MX(10, 'host.test-domain.com'),
            dns.Record_HINFO(os='Linux', cpu='A Fast One, Dontcha know'),
            dns.Record_CNAME('canonical.name.com'),
            dns.Record_MB('mailbox.test-domain.com'),
            dns.Record_MG('mail.group.someplace'),
            dns.Record_TXT('A First piece of Text', 'a SecoNd piece'),
            dns.Record_TXT('Some more text, haha!  Yes.  \0  Still here?'),
            dns.Record_MR('mail.redirect.or.whatever'),
            dns.Record_MINFO(rmailbx='r mail box', emailbx='e mail box'),
            dns.Record_AFSDB(subtype=1, hostname='afsdb.test-domain.com'),
            dns.Record_RP(mbox='whatever.i.dunno', txt='some.more.text'),
            dns.Record_WKS(0x12EF4303, socket.IPPROTO_TCP, '\x12\x01\x16\xfe\xc1\x00\x01'),
            soa_record
        ],
        'http.tcp.test-domain.com': [
            dns.Record_SRV(257, 16383, 43690, 'some.other.place.fool')
        ],
        'host.test-domain.com': [
            dns.Record_A('123.242.1.5'),
            dns.Record_A('0.255.0.255'),
        ],
        'host-two.test-domain.com': [
#
#  Python bug
#           dns.Record_A('255.255.255.255'),
#
            dns.Record_A('255.255.255.254'),
            dns.Record_A('0.0.0.0')
        ],
    }
)

reverse_domain = NoFileAuthority(
    soa = ('93.84.28.in-addr.arpa', reverse_soa),
    records = {
        '123.93.84.28.in-addr.arpa': [
             dns.Record_PTR('test.host-reverse.lookup.com'),
             reverse_soa
        ]
    }
)


class ServerDNSTestCase(unittest.DeferredTestCase):
    """Test cases for DNS server and client."""
    
    def setUp(self):
        self.factory = server.DNSServerFactory([
            test_domain_com, reverse_domain
        ], verbose=2)
        
        self.listenerTCP = reactor.listenTCP(PORT, self.factory)
        
        p = dns.DNSDatagramProtocol(self.factory)
        self.listenerUDP = reactor.listenUDP(PORT, p)
        
        self.resolver = client.Resolver(servers=[('127.0.0.1', PORT)])


    def tearDown(self):
        self.listenerTCP.stopListening()
        self.listenerUDP.stopListening()


    def namesTest(self, d, r):
        global gotResponse
        gotResponse = 0
        self.deferredFailUnlessEqual(d.addBoth(setDone), r)
        while not gotResponse:
            reactor.iterate(0.05)


    def testAddressRecord1(self):
        """Test simple DNS 'A' record queries"""
        self.namesTest(
            self.resolver.lookupAddress('test-domain.com'),
            [dns.Record_A('127.0.0.1')]
        )


    def testAddressRecord2(self):
        """Test DNS 'A' record queries with multiple answers"""
        self.namesTest(
            self.resolver.lookupAddress('host.test-domain.com'),
            [dns.Record_A('123.242.1.5'), dns.Record_A('0.255.0.255')]
        )


    def testAdressRecord3(self):
        """Test DNS 'A' record queries with edge cases"""
        self.namesTest(
            self.resolver.lookupAddress('host-two.test-domain.com'),
            [dns.Record_A('255.255.255.254'), dns.Record_A('0.0.0.0')]
        )


    def testAuthority(self):
        """Test DNS 'SOA' record queries"""
        self.namesTest(
            self.resolver.lookupAuthority('test-domain.com'),
            [soa_record]
        )


    def testMailExchangeRecord(self):
        """Test DNS 'MX' record queries"""
        self.namesTest(
            self.resolver.lookupMailExchange('test-domain.com'),
            [dns.Record_MX(10, 'host.test-domain.com')]
        )


    def testNameserver(self):
        """Test DNS 'NS' record queries"""
        self.namesTest(
            self.resolver.lookupNameservers('test-domain.com'),
            [dns.Record_NS('39.28.189.39')]
        )


    def testHINFO(self):
        """Test DNS 'HINFO' record queries"""
        self.namesTest(
            self.resolver.lookupHostInfo('test-domain.com'),
            [dns.Record_HINFO(os='Linux', cpu='A Fast One, Dontcha know')]
        )

    def testPTR(self):
        """Test DNS 'PTR' record queries"""
        self.namesTest(
            self.resolver.lookupPointer('123.93.84.28.in-addr.arpa'),
            [dns.Record_PTR('test.host-reverse.lookup.com')]
        )


    def testCNAME(self):
        """Test DNS 'CNAME' record queries"""
        self.namesTest(
            self.resolver.lookupCanonicalName('test-domain.com'),
            [dns.Record_CNAME('canonical.name.com')]
        )
 

    def testMB(self):
        """Test DNS 'MB' record queries"""
        self.namesTest(
            self.resolver.lookupMailBox('test-domain.com'),
            [dns.Record_MB('mailbox.test-domain.com')]
        )


    def testMG(self):
        """Test DNS 'MG' record queries"""
        self.namesTest(
            self.resolver.lookupMailGroup('test-domain.com'),
            [dns.Record_MG('mail.group.someplace')]
        )


    def testMR(self):
        """Test DNS 'MR' record queries"""
        self.namesTest(
            self.resolver.lookupMailRename('test-domain.com'),
            [dns.Record_MG('mail.redirect.or.whatever')]
        )


    def testMINFO(self):
        """Test DNS 'MINFO' record queries"""
        self.namesTest(
            self.resolver.lookupMailboxInfo('test-domain.com'),
            [dns.Record_MINFO(rmailbx='r mail box', emailbx='e mail box')]
        )


    def testSRV(self):
        """Test DNS 'SRV' record queries"""
        self.namesTest(
            self.resolver.lookupService('http.tcp.test-domain.com'),
            [dns.Record_SRV(257, 16383, 43690, 'some.other.place.fool')]
        )

    def testAFSDB(self):
        """Test DNS 'AFSDB' record queries"""
        self.namesTest(
            self.resolver.lookupAFSDatabase('test-domain.com'),
            [dns.Record_AFSDB(subtype=1, hostname='afsdb.test-domain.com')]
        )


    def testRP(self):
        """Test DNS 'RP' record queries"""
        self.namesTest(
            self.resolver.lookupResponsibility('test-domain.com'),
            [dns.Record_RP(mbox='whatever.i.dunno', txt='some.more.text')]
        )


    def testTXT(self):
        """Test DNS 'TXT' record queries"""
        self.namesTest(
            self.resolver.lookupText('test-domain.com'),
            [dns.Record_TXT('A First piece of Text', 'a SecoNd piece'),
             dns.Record_TXT('Some more text, haha!  Yes.  \0  Still here?')]
        )


    def testWKS(self):
        """Test DNS 'WKS' record queries"""
        self.namesTest(
            self.resolver.lookupWellKnownServices('test-domain.com'),
            [dns.Record_WKS(0x12EF4303, socket.IPPROTO_TCP, '\x12\x01\x16\xfe\xc1\x00\x01')]
        )


#    def testAAAA(self):
#        """Test DNS 'AAAA' record queries (IPv6)"""
#        self.namesTest(
#            self.resolver.lookupAddress6('test-domain.com'),
#            [dns.Record_AAAA('AF43:5634:1294:AFCB:56AC:48EF:34C3:01FF')]
#        )


#    def testZoneTransfer(self):
#        """Test DNS 'AXFR' queries (Zone transfer)"""
#        self.namesTest(
#            self.resolver.lookupZone('test-domain.com'),
#            test_domain_com
#        )
