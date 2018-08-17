#!/bin/sh
''''[ -z $LOG ] && export LOG=/dev/stdout # '''
''''which python2 >/dev/null && exec python2 -u "$0" "$@" >> $LOG 2>&1 # '''
''''which python  >/dev/null && exec python  -u "$0" "$@" >> $LOG 2>&1 # '''

# Copyright (C) 2014-2015 Nginx, Inc.

import sys, os, signal, base64, ldap, Cookie, argparse
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

#Listen = ('localhost', 8888)
#Listen = "/tmp/auth.sock"    # Also uncomment lines in 'Requests are
                              # processed with UNIX sockets' section below

# -----------------------------------------------------------------------------
# Different request processing models: select one
# -----------------------------------------------------------------------------
# Requests are processed in separate thread
import threading
from SocketServer import ThreadingMixIn
class AuthHTTPServer(ThreadingMixIn, HTTPServer):
    pass
# -----------------------------------------------------------------------------
# Requests are processed in separate process
#from SocketServer import ForkingMixIn
#class AuthHTTPServer(ForkingMixIn, HTTPServer):
#    pass
# -----------------------------------------------------------------------------
# Requests are processed with UNIX sockets
#import threading
#from SocketServer import ThreadingUnixStreamServer
#class AuthHTTPServer(ThreadingUnixStreamServer, HTTPServer):
#    pass
# -----------------------------------------------------------------------------

class AuthHandler(BaseHTTPRequestHandler):

    # Return True if request is processed and response sent, otherwise False
    # Set ctx['user'] and ctx['pass'] for authentication
    def do_GET(self):

        ctx = self.ctx
        print "........",ctx,'lllllllll',type(ctx)
        print '????????????????????',self.headers
        print '============================================\n'

        ctx['action'] = 'input parameters check'
        for k, v in self.get_params().items():
            ctx[k] = self.headers.get(v[0], v[1])
            if ctx[k] == None:
                self.auth_failed(ctx, 'required "%s" header was not passed' % k)
                return True

        ctx['action'] = 'performing authorization'
        auth_header = self.headers.get('Authorization')
        auth_cookie = self.get_cookie(ctx['cookiename'])
        print 'header is :\n',auth_header
        print 'cookie is :\n',auth_cookie

        if auth_cookie != None and auth_cookie != '':
            auth_header = "Basic " + auth_cookie
            self.log_message("using username/password from cookie %s" %
                             ctx['cookiename'])
        else:
            self.log_message("using username/password from authorization header")

        if auth_header is None or not auth_header.lower().startswith('basic '):

            self.send_response(401)
            print 'send 401 succ'
            self.send_header('WWW-Authenticate', 'Basic realm="' + ctx['realm'] + '"')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            print 'end headers ..........\n'

            return True

        ctx['action'] = 'decoding credentials'
        print 'begin to decode credentials\n'

        try:
            auth_decoded = base64.b64decode(auth_header[6:])
            print 'LLLLLLLLLLLLLLLLL',auth_decoded
            user, passwd = auth_decoded.split(':', 1)
            print 'user and password are:',user,passwd

        except:
            self.auth_failed(ctx)
            return True

        ctx['user'] = user
        ctx['pass'] = passwd

        # Continue request processing
        return False

    def get_cookie(self, name):
        cookies = self.headers.get('Cookie')
        if cookies:
            authcookie = Cookie.BaseCookie(cookies).get(name)
            if authcookie:
                return authcookie.value
            else:
                return None
        else:
            return None


    # Log the error and complete the request with appropriate status
    def auth_failed(self, ctx, errmsg = None):

        msg = 'Error while ' + ctx['action']
        if errmsg:
            msg += ': ' + errmsg

        ex, value, trace = sys.exc_info()

        if ex != None:
            msg += ": " + str(value)

        if ctx.get('url'):
            msg += ', server="%s"' % ctx['url']

        if ctx.get('user'):
            msg += ', login="%s"' % ctx['user']

        self.log_error(msg)
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="' + ctx['realm'] + '"')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

    def get_params(self):
        return {}

    def log_message(self, format, *args):
        if len(self.client_address) > 0:
            addr = BaseHTTPRequestHandler.address_string(self)
        else:
            addr = "-"

        if not hasattr(self, 'ctx'):
            user = '-'
        else:
            user = self.ctx['user']

        sys.stdout.write("%s - %s [%s] %s\n" % (addr, user,
                         self.log_date_time_string(), format % args))

    def log_error(self, format, *args):
        self.log_message(format, *args)


# Verify username/password against LDAP server
class LDAPAuthHandler(AuthHandler):
    # Parameters to put into self.ctx from the HTTP header of auth request
    params =  {
             # parameter      header         default
             'realm': ('X-Ldap-Realm', 'Restricted'),
             'url': ('X-Ldap-URL', None),
             'starttls': ('X-Ldap-Starttls', 'false'),
             'basedn': ('X-Ldap-BaseDN', None),
             'template': ('X-Ldap-Template', '(cn=%(username)s)'),
             'binddn': ('X-Ldap-BindDN', ''),
             'bindpasswd': ('X-Ldap-BindPass', ''),
             'cookiename': ('X-CookieName', '')
        }

    @classmethod
    def set_params(cls, params):
        cls.params = params

    def get_params(self):
        return self.params

    # GET handler for the authentication request
    def do_GET(self):

        ctx = dict()
        self.ctx = ctx

        ctx['action'] = 'initializing basic auth handler'
        ctx['user'] = '-'

        if AuthHandler.do_GET(self):
            print 'something is wrong\n'
            # request already processed
            return

        ctx['action'] = 'empty password check'
        print 'empty password check\n',ctx['pass'],ctx['url'],ctx['basedn']
        if not ctx['pass']:
            self.auth_failed(ctx, 'attempt to use empty password')
            print 'attempt to use empty\n'
            return

        try:
            print 'AAAAAAAAAAAAAAA begin to ldap auth\n'
            # check that uri and baseDn are set
            # either from cli or a request
            if not ctx['url']:
                self.log_message('LDAP URL is not set!')
                return
            if not ctx['basedn']:
                self.log_message('LDAP baseDN is not set!')
                return

            ctx['action'] = 'initializing LDAP connection'
            print 'begin to init ldap connection\n'
            try:
                print ">>>>>>>>>>>>>>>>>>",ctx['url']
                ldap_obj = ldap.initialize(ctx['url']);
                print ">>>>>>>>>>>>>>>>>>",ldap_obj,ctx['url']
            except:
                print 'There is something wrong\n'

            # Python-ldap module documentation advises to always
            # explicitely set the LDAP version to use after running
            # initialize() and recommends using LDAPv3. (LDAPv2 is
            # deprecated since 2003 as per RFC3494)
            #
            # Also, the STARTTLS extension requires the
            # use of LDAPv3 (RFC2830).
            ldap_obj.protocol_version=ldap.VERSION3

            # Establish a STARTTLS connection if required by the
            # headers.
            if ctx['starttls'] == 'true':
                ldap_obj.start_tls_s()

            # See http://www.python-ldap.org/faq.shtml
            # uncomment, if required
            # ldap_obj.set_option(ldap.OPT_REFERRALS, 0)

            ctx['action'] = 'binding as search user'
            bind_result = ldap_obj.bind_s(ctx['binddn'], ctx['bindpasswd'], ldap.AUTH_SIMPLE)
            print 'pppppppppppppppppppppppppp',bind_result

            ctx['action'] = 'preparing search filter'
#            searchfilter = ctx['template'] % { 'username': ctx['user'] }
            searchfilter = ('(&(emailAddress={0})(objectclass=ePerson))').format(ctx['user'])
            print 'serach filter is',searchfilter
            self.log_message(('searching on server "%s" with base dn ' + \
                              '"%s" with filter "%s"') %
                              (ctx['url'], ctx['basedn'], searchfilter))

            ctx['action'] = 'running search query'
#            results = ldap_obj.search_s(ctx['basedn'], ldap.SCOPE_SUBTREE, searchfilter, ['objectclass'], 1)
            results = ldap_obj.search_s(ctx['basedn'], ldap.SCOPE_SUBTREE, searchfilter)
            print "<<<<<<<<<<<<<<<",results,ctx['basedn'],searchfilter
            print 'uid for username',results[0][0] ,type(results[0][0])
            group_results = ldap_obj.search_s("cn=GRA_ADMIN,ou=memberlist,ou=ibmgroups,o=ibm.com",ldap.SCOPE_SUBTREE,"(objectclass=groupOfUniqueNames)")
            print 'member of Group is',group_results[0][1]['uniquemember'],type(group_results[0][1]['uniquemember'])
           
            ctx['action'] = 'verifying search query results'
 
            if results[0][0] in group_results[0][1]['uniquemember']:
                print 'user exist in group'
            else:
                print 'user does not exist in group'
                self.auth_failed(ctx, 'no objects found')
                return

#            if len(results) < 1:
 #               self.auth_failed(ctx, 'no objects found')
  #              return

            ctx['action'] = 'binding as an existing user'
            ldap_dn = results[0][0]
            ctx['action'] += ' "%s"' % ldap_dn
            ldap_obj.bind_s(ldap_dn, ctx['pass'], ldap.AUTH_SIMPLE)

            self.log_message('Auth OK for user "%s"' % (ctx['user']))

            # Successfully authenticated user
            self.send_response(200)
            self.end_headers()

        except:
            self.auth_failed(ctx)

def exit_handler(signal, frame):
    global Listen

    if isinstance(Listen, basestring):
        try:
            os.unlink(Listen)
        except:
            ex, value, trace = sys.exc_info()
            sys.stderr.write('Failed to remove socket "%s": %s\n' %
                             (Listen, str(value)))
            sys.stderr.flush()
    sys.exit(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="""Simple Nginx LDAP authentication helper.""")
    # Group for listen options:
    group = parser.add_argument_group("Listen options")
    group.add_argument('--host',  metavar="hostname",
#        default="localhost", help="host to bind (Default: localhost)")
        default="ngnix-ldap.rtp.raleigh.ibm.com",help="host to bind (Default: localhost)")
    group.add_argument('-p', '--port', metavar="port", type=int,
        default=8888, help="port to bind (Default: 8888)")
    # ldap options:
    group = parser.add_argument_group(title="LDAP options")
    group.add_argument('-u', '--url', metavar="URL",
        default="ldap://bluepages.ibm.com:389",
        help=("LDAP URI to query (Default: ldap://bluepages.ibm.com:389)"))
    group.add_argument('-s', '--starttls', metavar="starttls",
        default="false",
        help=("Establish a STARTTLS protected session (Default: false)"))
    group.add_argument('-b', metavar="baseDn", dest="basedn", default='ou=bluepages,o=ibm.com',
        help="LDAP base dn (Default: unset)")
    group.add_argument('-D', metavar="bindDn", dest="binddn", default='',
        help="LDAP bind DN (Default: anonymous)")
    group.add_argument('-w', metavar="passwd", dest="bindpw", default='',
        help="LDAP password for the bind DN (Default: unset)")
    group.add_argument('-f', '--filter', metavar='filter',
    #    default='(cn=%(username)s)',
        default = '(&(emailAddress=%s)(objectclass=ePerson))',
        help="LDAP filter (Default: cn=%%(username)s)")
    # http options:
    group = parser.add_argument_group(title="HTTP options")
    group.add_argument('-R', '--realm', metavar='"Restricted Area"',
        default="Restricted", help='HTTP auth realm (Default: "Restricted")')
    group.add_argument('-c', '--cookie', metavar="cookiename",
        default="", help="HTTP cookie name to set in (Default: unset)")

    args = parser.parse_args()
    global Listen
    Listen = (args.host, args.port)
    print "Listen port is ", Listen,args
    auth_params = {
             'realm': ('X-Ldap-Realm', args.realm),
             'url': ('X-Ldap-URL', args.url),
             'starttls': ('X-Ldap-Starttls', args.starttls),
             'basedn': ('X-Ldap-BaseDN', args.basedn),
             'template': ('X-Ldap-Template', args.filter),
             'binddn': ('X-Ldap-BindDN', args.binddn),
             'bindpasswd': ('X-Ldap-BindPass', args.bindpw),
             'cookiename': ('X-CookieName', args.cookie)
    }
    print "The params is ",auth_params
    LDAPAuthHandler.set_params(auth_params)
    server = AuthHTTPServer(Listen, LDAPAuthHandler)
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    sys.stdout.write("Start listening on %s:%d...\n" % Listen)
    sys.stdout.flush()
    server.serve_forever()
