#!/usr/bin/env python
"""
bot.py - Phenny IRC Bot
Copyright 2008, Sean B. Palmer, inamidst.com
Licensed under the Eiffel Forum License 2.

http://inamidst.com/phenny/
"""

import sys, os, re, threading, imp
import irc

home = os.getcwd()

def decode(bytes): 
   try: text = bytes.decode('utf-8')
   except UnicodeDecodeError:
      try: text = bytes.decode('iso-8859-1')
      except UnicodeDecodeError: 
         text = bytes.decode('cp1252')
   return text

class IrcBot (irc.Bot):

   def __init__(self, nick, name, channels, password, phenny):
      irc.Bot.__init__(self, nick, name, channels, password)
      self.phenny = phenny

   def dispatch(self, origin, args):
      self.phenny.dispatch(origin, args)

   def msg(self, recipient, origin, msg):
      irc.Bot.msg(self, recipient, msg)


import warnings

warnings.filterwarnings('ignore', 'the sha module is deprecated')
warnings.filterwarnings('ignore', 'the md5 module is deprecated')

from xmpp.client import Client
from xmpp.protocol import JID, Message, Presence, NS_MUC
import time

class XmppBot (object):
   '''In your ~/.phenny/default.py:

       xmpp = True
       xmpp_jid = 'phenny_bot@xmpp-host.example.com'
       xmpp_password = 'super-s3kr1t'

       # The following are then re-interpreted:
       nick = 'groupchat-nick'
       host = 'xmpp-host.example.com'
       port = 5223 # or whatever
       channels = [ '#phenny@conference.example.com', 'group-chat@conference.example.com' ]
   ''' # '

   def __init__(self, config, phenny):
      self.config = config
      self.phenny = phenny
      # setup

   def run(self):
      # connect, join, &c.
      # loop
      print 'running xmpp bot'
      self.jid = JID(self.config.xmpp_jid)
      self.client = Client(self.jid.getDomain(), debug=[])

      print 'connect',self.client.connect((self.config.host, self.config.port))
      print 'auth',self.client.auth(self.jid.getNode(), self.config.xmpp_password, resource=self.config.nick)

      self.client.RegisterHandler('message', self._message_cb)

      for channel in self.config.channels:
         muc_me = '%(channel)s/%(nick)s' % {'channel':channel, 'nick':self.config.nick}
         p = Presence(to=muc_me)
         p.setTag('x', namespace=NS_MUC) #.setTagData('password','')
         id = self.client.send(p)
         print 'sent presence id %s for channel %s' % (id,muc_me)

      while 1:
         self.client.Process(1)
      
   def _message_cb(self, session, msg):
      # print u'got msg',msg.getBody()
      class XmppOrigin (object):
         def __init__(self):
            self.nick = msg.getFrom().getResource()
            self.user = msg.getFrom().getNode()
            self.host = msg.getFrom().getDomain()
            self.sender = msg.getFrom()
            self.is_groupchat_message = (msg.getType() == 'groupchat')
            self.msg = msg
      origin = XmppOrigin()
      args = (msg.getBody(), 'PRIVMSG', ())
      # print u'dispatching', origin, args
      self.phenny.dispatch(origin, args)

   def msg(self, recipient, origin, text):
      # print u'message to [%s]: [%s] was originally [%s]' % (recipient, text, str(origin))
      msg_type = 'chat'
      try:
         if (type(origin) == type(True) and origin) \
                or (origin and origin.msg.getType() == 'groupchat'):
            msg_type = 'groupchat'
      except:
         print 'origin %s %s' % (type(origin),str(origin))
      self.client.send(Message(recipient, text, typ=msg_type))

   # def write(self, args, text=None): 
   # def dispatch(self, origin, args):
   # def msg(self, recipient, text): 
   # def error(self, origin): 

class Phenny (object):
   def __init__(self, config):
      self.useXmpp = False
      try:
         self.useXmpp = config.xmpp
      except AttributeError:
         pass
      if self.useXmpp:
         self.bot = XmppBot(config, self)
      else:
         self.bot = IrcBot(config.nick, config.name, config.channels, config.password, self)
      self.config = config
      self.doc = {}
      self.stats = {}

      self.nick = config.nick
      self.user = config.nick
      self.name = config.name
      self.password = config.password

      self.verbose = True
      self.channels = config.channels or []

      self.setup()

   def run(self, host, port):
      if self.useXmpp:
         self.bot.run()
      else:
         self.bot.run(host, port)

   def write(self, args, text=None):
      print 'error: write called'
      self.bot.write(args, text)

   def msg(self, recipient, origin, text):
      self.bot.msg(recipient, origin, text)

   def error(self, origin): 
      try: 
         import traceback
         trace = traceback.format_exc()
         print trace
         lines = list(reversed(trace.splitlines()))

         report = [lines[0].strip()]
         for line in lines: 
            line = line.strip()
            if line.startswith('File "/'): 
               report.append(line[0].lower() + line[1:])
               break
         else: report.append('source unknown')

         self.bot.msg(origin.sender, origin, report[0] + ' (' + report[1] + ')')
      except:
         self.bot.msg(origin.sender, origin, "Got an error.")

   def setup(self): 
      self.variables = {}

      filenames = []
      if not hasattr(self.config, 'enable'): 
         for fn in os.listdir(os.path.join(home, 'modules')): 
            if fn.endswith('.py') and not fn.startswith('_'): 
               filenames.append(os.path.join(home, 'modules', fn))
      else: 
         for fn in self.config.enable: 
            filenames.append(os.path.join(home, 'modules', fn + '.py'))

      if hasattr(self.config, 'extra'): 
         for fn in self.config.extra: 
            if os.path.isfile(fn): 
               filenames.append(fn)
            elif os.path.isdir(fn): 
               for n in os.listdir(fn): 
                  if n.endswith('.py') and not n.startswith('_'): 
                     filenames.append(os.path.join(fn, n))

      modules = []
      excluded_modules = getattr(self.config, 'exclude', [])
      for filename in filenames: 
         name = os.path.basename(filename)[:-3]
         if name in excluded_modules: continue
         # if name in sys.modules: 
         #    del sys.modules[name]
         try: module = imp.load_source(name, filename)
         except Exception, e: 
            print >> sys.stderr, "Error loading %s: %s (in bot.py)" % (name, e)
         else: 
            if hasattr(module, 'setup'): 
               module.setup(self)
            self.register(vars(module))
            modules.append(name)

      if modules: 
         print >> sys.stderr, 'Registered modules:', ', '.join(modules)
      else: print >> sys.stderr, "Warning: Couldn't find any modules"

      self.bind_commands()

   def register(self, variables): 
      # This is used by reload.py, hence it being methodised
      for name, obj in variables.iteritems(): 
         if hasattr(obj, 'commands') or hasattr(obj, 'rule'): 
            self.variables[name] = obj

   def bind_commands(self): 
      self.commands = {'high': {}, 'medium': {}, 'low': {}}
      
      def bind(self, priority, regexp, func): 
         print priority, regexp.pattern.encode('utf-8'), func
         # register documentation
         if not hasattr(func, 'name'): 
            func.name = func.__name__
         if func.__doc__: 
            if hasattr(func, 'example'): 
               example = func.example
               example = example.replace('$nickname', self.nick)
            else: example = None
            self.doc[func.name] = (func.__doc__, example)
         self.commands[priority].setdefault(regexp, []).append(func)

      def sub(pattern, self=self): 
         # These replacements have significant order
         pattern = pattern.replace('$nickname', re.escape(self.nick))
         return pattern.replace('$nick', r'%s[,:] +' % re.escape(self.nick))

      for name, func in self.variables.iteritems(): 
         # print name, func
         if not hasattr(func, 'priority'): 
            func.priority = 'medium'

         if not hasattr(func, 'thread'): 
            func.thread = True

         if not hasattr(func, 'event'): 
            func.event = 'PRIVMSG'
         else: func.event = func.event.upper()

         if hasattr(func, 'rule'): 
            if isinstance(func.rule, str): 
               pattern = sub(func.rule)
               regexp = re.compile(pattern)
               bind(self, func.priority, regexp, func)

            if isinstance(func.rule, tuple): 
               # 1) e.g. ('$nick', '(.*)')
               if len(func.rule) == 2 and isinstance(func.rule[0], str): 
                  prefix, pattern = func.rule
                  prefix = sub(prefix)
                  regexp = re.compile(prefix + pattern)
                  bind(self, func.priority, regexp, func)

               # 2) e.g. (['p', 'q'], '(.*)')
               elif len(func.rule) == 2 and isinstance(func.rule[0], list): 
                  prefix = self.config.prefix
                  commands, pattern = func.rule
                  for command in commands: 
                     command = r'(%s)\b(?: +(?:%s))?' % (command, pattern)
                     regexp = re.compile(prefix + command)
                     bind(self, func.priority, regexp, func)

               # 3) e.g. ('$nick', ['p', 'q'], '(.*)')
               elif len(func.rule) == 3: 
                  prefix, commands, pattern = func.rule
                  prefix = sub(prefix)
                  for command in commands: 
                     command = r'(%s) +' % command
                     regexp = re.compile(prefix + command + pattern)
                     bind(self, func.priority, regexp, func)

         if hasattr(func, 'commands'): 
            for command in func.commands: 
               template = r'^%s(%s)(?: +(.*))?$'
               pattern = template % (self.config.prefix, command)
               regexp = re.compile(pattern)
               bind(self, func.priority, regexp, func)

   def wrapped(self, origin, text, match): 
      class PhennyWrapper(object): 
         def __init__(self, phenny): 
            self.bot = phenny

         def __getattr__(self, attr): 
            sender = origin.sender or text
            if attr == 'reply': 
               return (lambda msg: 
                  self.bot.bot.msg(sender, origin, origin.nick + ': ' + msg))
            elif attr == 'say': 
               return lambda msg: self.bot.bot.msg(sender, origin, msg)
            elif attr == 'msg':
               return lambda sender,msg: self.bot.bot.msg(sender, origin, msg)
            return getattr(self.bot, attr)

      return PhennyWrapper(self)

   def input(self, origin, text, bytes, match, event, args): 
      class CommandInput(unicode): 
         def __new__(cls, text, origin, bytes, match, event, args): 
            s = unicode.__new__(cls, text)
            s.sender = origin.sender
            s.nick = origin.nick
            s.event = event
            s.bytes = bytes
            s.match = match
            s.group = match.group
            s.groups = match.groups
            s.args = args
            s.admin = origin.nick in self.config.admins
            s.owner = origin.nick == self.config.owner
            s.is_groupchat_message = origin.is_groupchat_message
            return s

      return CommandInput(text, origin, bytes, match, event, args)

   def call(self, func, origin, phenny, input): 
      try: func(phenny, input)
      except Exception, e: 
         self.error(origin)

   def limit(self, origin, func):
      if origin.sender and origin.is_groupchat_message:
         if hasattr(self.config, 'limit'): 
            limits = self.config.limit.get(origin.sender)
            if limits and (func.__module__ not in limits): 
               return True
      return False

   def dispatch(self, origin, args): 
      bytes, event, args = args[0], args[1], args[2:]
      text = decode(bytes)

      for priority in ('high', 'medium', 'low'): 
         items = self.commands[priority].items()
         for regexp, funcs in items: 
            for func in funcs: 
               if event != func.event: continue

               match = regexp.match(text)
               if match: 
                  if self.limit(origin, func): continue

                  phenny = self.wrapped(origin, text, match)
                  input = self.input(origin, text, bytes, match, event, args)

                  if func.thread: 
                     targs = (func, origin, phenny, input)
                     t = threading.Thread(target=self.call, args=targs)
                     t.start()
                  else: self.call(func, origin, phenny, input)

                  for source in [origin.sender, origin.nick]: 
                     try: self.stats[(func.name, source)] += 1
                     except KeyError: 
                        self.stats[(func.name, source)] = 1

if __name__ == '__main__': 
   print __doc__
