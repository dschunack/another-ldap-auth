import ldap
import time
import re
import logging
from itertools import repeat

class Aldap:
	def __init__(self, ldapEndpoint, dnUsername, dnPassword, serverDomain, searchBase, searchFilter, groupCaseSensitive, groupConditional):
		self.ldapEndpoint = ldapEndpoint
		self.searchBase = searchBase
		self.dnUsername = dnUsername
		self.dnPassword = dnPassword
		self.serverDomain = serverDomain
		self.searchFilter = searchFilter
		self.username = ''
		self.password = ''
		self.groupCaseSensitive = groupCaseSensitive
		self.groupConditional = groupConditional.lower()

		ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER )
		ldap.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
		self.connect = ldap.initialize(self.ldapEndpoint)
		self.connect.set_option(ldap.OPT_REFERRALS, 0)
		self.connect.set_option(ldap.OPT_DEBUG_LEVEL, 255)

		self.log = logging.getLogger('ALDAP')

	def setUser(self, username, password):
		self.username = username
		self.password = password
		# Replace in the filter the variable "{username}" for the username
		finalUsername = re.sub(r'^.+\\','', self.username)
		self.searchFilter = self.searchFilter.replace("{username}", finalUsername)

	def search(self):
		self.log.debug(f"Searching Groups by filter: {self.searchFilter}")

		start = time.time()
		result = ""
		try:
			self.connect.simple_bind_s(self.username, self.password)
			# Org not working
			#self.connect.simple_bind_s("self.dnUsername", self.dnPassword)
			result = self.connect.search_s(self.searchBase, ldap.SCOPE_SUBTREE, self.searchFilter)
			#self.connect.unbind_s()
		except ldap.LDAPError as e:
			self.log.error("There was an error when trying to bind for groups search.")
			self.log.error(e)

		self.log.info(f"Time: {time.time()-start}")
		return result
        
		self.log.debug(f"Objects of User: {result!r}")

	def decode(self, word:bytes):
		return word.decode("utf-8")

	def findMatch(self, matchGroup:str, userGroup:str):
		# Extract the Common Name from the string (letters, spaces and underscores)
		userGroup = re.match('CN=((\w*\s?_?]*)*)', userGroup).group(1)

		if not self.groupCaseSensitive:
			userGroup = userGroup.lower()
			matchGroup = matchGroup.lower()

		# return match against supplied group/pattern (None if there is no match)
		try:
			return re.fullmatch(f'{matchGroup}.*', userGroup).group(0)
		except:
			return None

	# Validate the groups in the Active Directory tree
	def validateGroups(self, groups):
		tree = self.search()

		# Crawl tree and extract the groups of the user
		userGroups = []
		for zone in tree:
			for element in zone:
				try:
					userGroups.extend(element['memberOf'])
				except TypeError:
					None
		userGroups = list(map(self.decode,userGroups))
		
		self.log.debug(f"List User groups: {userGroups!r}")

		self.log.info(f"Validating the following groups: {groups}")
		self.log.info(f"Conditional: {self.groupConditional}")

		# List for the matches groups
		matchedGroups = []
		matchesByGroup = []
		for group in groups:
			# apply find match function to each value and then remove None values
			matches = list(filter(None,list(map(self.findMatch, repeat(group), userGroups))))
			if matches:
				matchesByGroup.append((group,matches))
				matchedGroups.extend(matches)

		self.log.info(f"Matched groups: {matchedGroups}")

		# Conditiona OR, true if just 1 group match
		if self.groupConditional == 'or':
			if matchedGroups:
				self.log.info("One of the groups is valid for the user.")
				return True,matchedGroups
		# Conditiona AND, true if all the groups match
		elif self.groupConditional == 'and':
			if len(groups) == len(matchesByGroup):
				self.log.info("All groups are valid for the user.")
				return True,matchedGroups
		else:
			self.log.warning("Invalid group conditional.")
			return False,[]

		self.log.warning("Invalid groups.")
		return False,[]

	def authenticateUser(self):
		finalUsername = self.username
		if self.serverDomain:
			# The configuration has serverDomain the username is username@domain
			finalUsername = self.username+"@"+self.serverDomain

		self.log.info(f"Authenticating user: {finalUsername}")

		start = time.time()
		try:
			self.connect.simple_bind_s(finalUsername, self.password)
			self.connect.unbind_s()
			self.log.info(f"Username valid: {finalUsername}")
			self.log.info(f"Time: {time.time()-start}")
			return True
		except ldap.INVALID_CREDENTIALS:
			self.log.warning("Invalid credentials.")
		except ldap.LDAPError as e:
			self.log.error("There was an error trying to bind.")
			self.log.error(e)

		return False
