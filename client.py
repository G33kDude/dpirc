#! /usr/bin/env python3

import json
import re
import socket
import sys
import threading
import time
import tkinter as tk

from datetime import datetime

IRCRE = ('^(?::(\S+?)(?:!(\S+?))?(?:@(\S+?))? )?' # Nick!User@Host
	+ '(\S+)(?: (?!:)(.+?))?(?: :(.+))?$') # CMD Params Params :Message

class IRC(object):
	def connect(self, server, port, nick, user=None, name=None):
		self.nick = nick
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.settimeout(260) # TODO: Settings
		self.sock.connect((server, port))
		self.send('NICK {}'.format(nick))
		self.send('USER {} 0 * :{}'.format(user or nick, name or nick))
		self.channels = {}
	def send(self, text):
		# TODO: Make sure not longer than 512
		self.sock.send((text + '\r\n').encode('UTF-8'))
		self.log('>{}'.format(text), raw=True)
		return text
	def sendcmd(self, cmd, params=[], msg=None):
		if len(params): cmd += ' ' + ' '.join(params)
		if msg is not None: cmd += ' :' + msg
		return self.send(cmd)
	def mainloop(self):
		buffer = b''
		while True:
			try:
				buffer += self.sock.recv(2048)
			except socket.timeout:
				pass # should reconnect
			lines = buffer.split(b'\r\n')
			buffer = lines.pop()
			for line in lines:
				line = line.decode('utf-8', 'replace') # TODO: Encoding settings
				self.log('<{}'.format(line), raw=True)
				self.handle_message(line)
	def handle_message(self, message):
		matched = re.match(IRCRE, message)
		nick, user, host, cmd, params, msg = matched.groups()
		if hasattr(self, 'on'+cmd):
			handler = getattr(self,'on'+cmd)
			handler(nick, user, host, cmd, (params or '').split(' '), msg)
	def onPING(self, nick, user, host, cmd, params, msg):
		self.sendcmd('PONG', msg=msg)

class Client(IRC):
	def __init__(self, server, port, nick, user=None, name=None):
		self.nick = nick
		self.master = tk.Tk()
		self.rawlog = tk.Text(self.master, state=tk.DISABLED)
		self.rawlog.pack(fill=tk.BOTH, expand=1)
		self.chanbox = tk.Listbox(self.master)
		self.chanbox.pack(fill=tk.Y, side=tk.LEFT)
		self.chanbox.bind('<<ListboxSelect>>', self.chanboxclick)
		self.nickbox = tk.Listbox(self.master)
		self.nickbox.pack(fill=tk.Y, side=tk.RIGHT)
		self.chatlog = tk.Text(self.master, state=tk.DISABLED)
		self.chatlog.pack(fill=tk.BOTH, expand=1)
		self.activechan = tk.Label(self.master, text=name)
		self.activechan.pack(side=tk.LEFT)
		self.chatbox = tk.Entry(self.master)
		self.chatbox.pack(fill=tk.X, side=tk.BOTTOM)
		self.chatbox.focus_set()
		self.master.bind('<Return>', self.chatboxsend)
		self.cur_chan = self.nick
		self.connect(server, port, nick, user, name)
	def chanboxclick(self, event):
		sel = self.chanbox.curselection()
		self.set_chan(sorted(self.channels)[sel[0]])
	def chatboxsend(self, event):
		msg = self.chatbox.get()
		self.chatbox.delete(0, tk.END)
		if not msg.startswith('/'):
			self.log('{} <{}> {}'.format(self.cur_chan, self.nick, msg))
			self.sendcmd('PRIVMSG', [self.cur_chan], msg)
			return
		split = msg[1:].split(' ', 2)
		command = split[0].lower()
		if command in ('join', 'j'):
			self.sendcmd('JOIN', [split[1]])
		elif command in ('part', 'p', 'leave'):
			chan = self.cur_chan if len(split) < 2 else split[1]
			self.sendcmd('PART', [chan])
		elif command in ('msg', 'pm'):
			self.sendcmd('PRIVMSG', [split[1]], split[2])
		elif command in ('quit', 'q', 'exit'):
			self.sendcmd('QUIT')
			sys.exit()
		elif command in ('raw', 'quote'):
			self.send(msg[1:].split(' ',1)[1])
		elif command in ('names', 'nicks', 'users'):
			self.log(', '.join(self.channels[self.cur_chan]))
		elif command in ('chan', 'channel', 'chans', 'channels', 'listchans'):
			if len(split) < 2:
				self.log(', '.join(self.channels))
				self.log('Type /chan #channel to switch active channels')
			elif split[1] in self.channels:
				self.set_chan(split[1])
			else:
				self.log('')
		else:
			self.log("UNKNOWN COMMAND: {}".format(command))
	def log(self, text, raw=False):
		log = self.rawlog if raw else self.chatlog
		log.config(state=tk.NORMAL)
		log.insert(tk.END, datetime.now().strftime('[%H:%M] ') + text + '\n')
		log.config(state=tk.DISABLED)
		log.see(tk.END)
	def onPRIVMSG(self, nick, user, host, cmd, params, msg):
		self.log('{} <{}> {}'.format(params[0], nick, msg))
	def onJOIN(self, nick, user, host, cmd, params, msg):
		channel = params[0]
		self.log('{} has joined {} ({}@{})'.format(nick, channel, user, host))
		if nick == self.nick:
			self.channels[channel] = []
			self.update_chans()
			self.set_chan(channel)
		if nick not in self.channels[channel]:
			self.channels[channel].append(nick)
		if channel == self.cur_chan:
			self.update_nicks()
	def onPART(self, nick, user, host, cmd, params, msg):
		channel = params[0]
		self.log('{} has parted {} ({}@{})'.format(nick, channel, user, host))
		if nick == self.nick:
			self.channels.pop(channel)
			print(sorted(self.channels))
			if channel == self.cur_chan:
				self.set_chan(sorted(self.channels)[0])
			self.update_chans()
		else:
			self.channels[channel].remove(nick)
			if channel == self.cur_chan:
				self.update_nicks()
	def onQUIT(self, nick, user, host, cmd, params, msg):
		for channel in self.channels:
			if nick not in self.channels[channel]:
				continue
			self.channels[channel].remove(nick)
			if channel == self.cur_chan:
				self.update_nicks()
	def on353(self, nick, user, host, cmd, params, msg):
		for nick in msg.split(' '):
			nick = nick.lstrip('@+') # TODO: Pull from server meta
			if nick not in self.channels[params[2]]:
				self.channels[params[2]].append(nick)
	def on366(self, nick, user, host, cmd, params, msg):
		self.update_nicks()
	def set_chan(self, channel):
		self.cur_chan = channel
		self.activechan.config(text=self.cur_chan)
		self.update_nicks()
	def update_nicks(self):
		self.nickbox.delete(0, tk.END)
		for nick in sorted(self.channels[self.cur_chan]):
			self.nickbox.insert(tk.END, nick)
	def update_chans(self):
		self.chanbox.delete(0, tk.END)
		for channel in sorted(self.channels):
			self.chanbox.insert(tk.END, channel)

def main():
	with open('config.json', 'r') as f:
		config = json.loads(f.read())
	client = Client(config['serv'], config['port'],
		config['nick'], config['user'], config['name'])
	client.sendcmd('JOIN', [config['chan']])
	x = threading.Thread(target=client.mainloop)
	x.daemon = True
	x.start()
	client.master.mainloop()

if __name__ == '__main__':
	main()
