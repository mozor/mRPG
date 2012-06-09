#!/usr/bin/env python

# mRPG
# https://github.com/mozor/mRPG
# Version 0.31
#
# Copyright 2012 Greg (NeWtoz@mozor.net) & Richard (richard@mozor.net);
# This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
# To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ or send a letter to
# Creative Commons, 444 Castro Street, Suite 900, Mountain View, California, 94041, USA.

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, task, defer
from twisted.python import log
from twisted.enterprise import adbapi
import time, sys, random, math
import ConfigParser
import sqlite3 as lite
from passlib.hash import sha512_crypt as sc

# Global Variables
is_started = 0
min_schema_ver_needed = 0.32

class mrpg:
    def __init__(self, parent):

        global mrpg_ref

        self.parent = parent
        self.channel = parent.factory.channel
        self.l = task.LoopingCall(self.rpg)
        self.loc = task.LoopingCall(self.location)
        self.loc2 = task.LoopingCall(self.updateLocationDaily)
        self.db = DBPool('mrpg.db')
        mrpg_ref = self
        self.db.mrpg = self

    @defer.inlineCallbacks
    def start(self):
        self.msg("Starting mRPG")
        print "Starting mRPG"
        self.msg("Please standby")
        print "Please standby"
        online = 0
        s = yield self.db.executeQuery("UPDATE users SET online = ?",online)
        # Start the reactor task that repeatedly loops through actions
        self.l.start(timespan)
        self.loc.start(movespan)
        self.loc2.start(86400)
        global is_started
        is_started = 1
        self.msg("Initialization complete")
        print "Initialization complete"

    def stop(self):
        self.msg("I think my loop needs to stop")
        self.l.stop()
        self.loc.stop()
        global is_started
        is_started = 0
        self.msg("It stopped")
        sys.exit()

    def msg(self, msg):
        self.parent.msg(self.channel, msg)

    def privateMessage(self, user, msg):
        if self.factory.use_private_message == 1:
            self.msg(user, msg)
        else:
            self.notice(user, msg)

    @defer.inlineCallbacks
    def performPenalty(self, user, reason):
        self.db = DBPool('mrpg.db')
        self.db.mrpg = self
        # print "in penalty function"
        global is_started
        # print is_started
        if is_started == 1:
            # print "is_started"
            is_online = yield self.db.is_user_online(user)
            if is_online:
                # print "isonline"
                if is_online[0][0] == 1:
                    # print "really is online"
                    self.msg(user + " has earned a penalty for: " + reason)
                    self.db.updateUserTimeMultiplier(user, penalty_constant)
                    self.db.getSingleUser(user)
        self.db.shutdown("")

    def writetofile(self, message):
        with open('output','a') as f:
            message = str(message)
            timestamp = time.strftime("[%b %d, %Y - %X] ")
            f.write("%s%s\n" % (timestamp, message))

    @defer.inlineCallbacks
    def doevent(self):
        entropy = self.parent.factory.event_randomness
        rand = random.randrange(1,100)

        db = DBPool('mrpg.db')
        db.mrpg = self

        if(rand <= entropy):
            # print "running event"
            event = yield db.get_event()
            user = yield db.get_random_user(1)

            if event and user:

                name = event[0][0]
                type = event[0][1]
                modifier = event[0][2]
                username = user[0][0]

                ttl = yield db.get_user_ttl(username)

                if ttl:
                    diff = ttl[0][0] * modifier - ttl[0][0]
                    message = "A " + str(type) + " occurred!"
                    self.msg(message)
                    message = str(username) + " " + str(name) + "."
                    self.msg(message)

                    db.updateUserTimeMultiplier(str(username), modifier)


                    if(diff > 0):
                        message = str(diff) + " seconds has been added to " + str(username) + "'s time"
                    else:
                        message = str(diff * -1) + " seconds has been removed from " + str(username) + "'s time"
                    self.msg(message)
        db.shutdown("")

    @defer.inlineCallbacks
    def doitems(self):
        entropy = self.parent.factory.item_randomness
        rand = random.randrange(1,100)

        db = DBPool('mrpg.db')
        db.mrpg = self

        if(rand <= entropy):
            event = yield db.executeQuery('''      SELECT t.item_description
                                                         ,i.item_name
                                                         ,i.modifier
                                                         ,i.special
                                                         ,u.username
                                                         ,u.level
                                                         ,t.id
                                                         ,i.id
                                                         ,iu.item_type
                                                     FROM items i
                                                          INNER JOIN users u
                                                                  ON u.username = (SELECT username
                                                                                     FROM users
                                                                                    WHERE online = 1
                                                                                 ORDER BY RANDOM() LIMIT 1)
                                                          INNER JOIN item_type t
                                                                  ON i.item_type = t.id
                                                          LEFT OUTER JOIN items_user iu
                                                                  ON u.username = iu.username
                                                                 AND t.id = iu.item_type
                                                 ORDER BY RANDOM() LIMIT ?''', 1)

            if event:

                item_description = event[0][0]
                item_name = event[0][1]
                modifier = event[0][2]
                special = event[0][3]
                username = event[0][4]
                level = event[0][5]
                item_type = event[0][6]
                item_id = event[0][7]
                user_has_item_type = str(event[0][8])

                if str(username) != "None":


                    rand = random.randrange(math.floor(int(level) / 2), level)

                    if rand < 1:
                        rand = 1

                    if user_has_item_type == "None":

                        query =  '''INSERT INTO items_user
                                               (username
                                               ,item_id
                                               ,item_type
                                               ,level)
                                        VALUES (?
                                               ,?
                                               ,?
                                               ,?)'''

                        s = yield db.executeQuery(query,(username, item_id, item_type, rand))

                        message = str(username) + " found a "  + str(item_name) + " level " + str(rand) + " " + str(item_description) + ", an item they were currently without!"
                    else:
                        s = yield db.executeQuery("UPDATE items_user SET item_id = ?, level = ? WHERE username = ? AND item_type = ?",(item_id, rand, username, item_type))

                        message = str(username) + " found a "  + str(item_name) + " level " + str(rand) + " " + str(item_description)

                    self.msg(message)

        db.shutdown("")


    def rpg(self):
        self.db = DBPool('mrpg.db')
        self.db.mrpg = self
        self.db.updateAllUsersTime(timespan * -1)
        self.db.shutdown("")

        self.db = DBPool('mrpg.db')
        self.db.mrpg = self
        self.db.levelUp()
        self.db.shutdown("")

        self.db = DBPool('mrpg.db')
        self.db.mrpg = self
        self.doevent()
        self.doitems()
        self.db.shutdown("")

        # self.db.getAllUsers()

        # self.db.shutdown("")

    def location(self):
        self.updateLocation()

    @defer.inlineCallbacks
    def updateLocation(self):
        dist = movespan * walking_speed / 3600.00000
        self.db = DBPool('mrpg.db')
        self.db.mrpg = self
        s = yield self.db.executeQuery("UPDATE users SET path_ttl = path_ttl - ? WHERE online = 1",movespan)
        temp = yield self.db.executeQuery("SELECT username, path_ttl, path_endpointx, path_endpointy, cordx, cordy, char_name FROM users WHERE online = 1","NONE")
        for s in temp:
            lat1 = math.radians(float(s[4]))
            long1 = math.radians(float(s[5]))
            lat2 = math.radians(float(s[2]))
            long2 = math.radians(float(s[3]))

            bear = math.atan2(math.sin(long2-long1)*math.cos(lat2), math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(long2 - long1))
            destx = math.asin( math.sin(lat1) * math.cos(dist/world_radius) + math.cos(lat1) * math.sin(dist/world_radius) * math.cos(bear) )
            desty = long1 + math.atan2( math.sin(bear) * math.sin(dist/world_radius) * math.cos(lat1), math.cos(dist/world_radius) - math.sin(lat1)*math.sin(destx) )

            destx = round(math.degrees(destx),5)
            desty = round(math.degrees(desty),5)

            t = yield self.db.executeQuery("UPDATE users SET cordx = ?, cordy = ? WHERE username = ?",(destx,desty,s[0]))

            if s[1] <= 0:
                gpsx = random.randint(-9000000,9000000)/100000.0
                gpsy = random.randint(-18000000,18000000)/100000.0
                self.db.executeQuery("UPDATE users SET path_ttl = 86400, path_endpointx = ?, path_endpointy = ? where username = ?",(gpsx, gpsy, s[0]))

            self.db.executeQuery("INSERT INTO movement_history (char_name,x,y) VALUES (?,?,?)",(s[6],destx,desty))
        self.db.shutdown('')

    @defer.inlineCallbacks
    def updateLocationDaily(self):
        temp = yield self.db.executeQuery("SELECT username, path_ttl, path_endpointx, path_endpointy, cordx, cordy FROM users WHERE online = 1","NONE")
        for s in temp:
            #if chance = 1: stay on path, 2: choose different path, 3: stay put.
            chance = random.randint(1,3)
            if chance == 1:
                pass
            elif chance == 2:
                gpsx = random.randint(-9000000,9000000)/100000.0
                gpsy = random.randint(-18000000,18000000)/100000.0
                self.db = DBPool('mrpg.db')
                self.db.executeQuery("UPDATE users SET path_endpointx = ?, path_endpointy = ? WHERE username = ?",(gpsx, gpsy, s[0]))
                self.db.shutdown('')
            elif chance == 3:
                self.db = DBPool('mrpg.db')
                self.db.mrpg = self
                self.db.executeQuery("UPDATE users SET path_endpointx = ?, path_endpointy = ? WHERE username = ?",(s[4],s[5],s[0]))
                self.db.shutdown('')

class DBPool:
    """
        Sqlite connection pool
    """
    def __init__(self, dbname):
    #        global mrpg_ref
    #        if mrpg_ref in globals():
    #            self.mrpg = mrpg_ref
        self.dbname = dbname
        self.__dbpool = adbapi.ConnectionPool('sqlite3', self.dbname, check_same_thread=False)

    def shutdown(self, callback_msg):
        """
            Shutdown function
            It's a required task to shutdown the database connection pool:
                garbage collector doesn't shutdown associated thread
        """
        self.__dbpool.close()

    def getSingleUser(self, user):
        query = "SELECT * FROM users WHERE username = ?"
        s = self.__dbpool.runQuery(query, (user,)).addCallback(self.showUser)

    def getAllUsers(self):
        query = "SELECT * FROM users WHERE online = 1"
        s = self.__dbpool.runQuery(query).addCallback(self.showUser)

    def showUser(self, output):
        for i in output:
            message = str(i[1]) + " will reach the next level in " + str(i[6]) + " seconds."
            mrpg_ref.msg(message)
            # print message

    def levelUp(self):
        query = "SELECT username, char_name, level, ttl FROM users WHERE ttl < 0 AND online = 1"
        s = self.__dbpool.runQuery(query).addCallback(self.showLevelUp)

    def showLevelUp(self, output):
        global mrpg_ref
        for i in output:
            user = str(i[0])
            char_name = str(i[1])
            level = int(i[2])

            new_level = level + 1
            ttl = min_time * new_level

            message = char_name + " has reached level " +str(new_level)
            #TODO fix these two messages
            mrpg_ref.msg(message)
            message = char_name + " will reach the next level in " +str(ttl) + " seconds"
            mrpg_ref.msg(message)

            self.db = self.__init__('mrpg.db')
            self.levelUpUser(char_name, level)
            self.shutdown("")
            #message = char_name + " has reached level " +str(new_level)
            #mrpg_ref.msg(message)

    def getResults(self, output):
        return output

    def executeQuery(self, query, args):
        if args == "NONE":
            return self.__dbpool.runQuery(query)
        if (type(args) is tuple):
            return self.__dbpool.runQuery(query, (args))
        else:
            return self.__dbpool.runQuery(query, [args])

    def levelUpUser(self, char_name, level):
        new_level = level + 1
        ttl = min_time * new_level
        return self.__dbpool.runQuery("UPDATE users SET ttl = ?, level = ? WHERE char_name = ?", (ttl, new_level, char_name))

    def updateUserTime(self, user, amount):
        return self.__dbpool.runOperation("UPDATE users SET ttl = ttl + ? WHERE username = ?", (amount, user,))

    def updateUserTimeMultiplier(self, user, amount):
        return self.__dbpool.runOperation("UPDATE users SET ttl = ROUND(ttl * ?,0) WHERE username = ?", (amount, user,))

    def updateAllUsersTime(self, amount):
        query = 'UPDATE users SET ttl = ttl + ? WHERE online = 1'
        return self.__dbpool.runQuery(query, [amount])

    def register_char(self, user, reg_char_name, reg_password, reg_char_class, hostname):
        query = 'INSERT INTO `users` (username,char_name,password,char_class,hostname,level,ttl,online,path_endpointx,path_endpointy,cordx,cordy,path_ttl,admin) VALUES (?,?,?,?,?,1,?,1,0,0,10,10,0,0)'
        return self.__dbpool.runQuery(query, (user, reg_char_name, reg_password, reg_char_class, hostname, min_time))

    def get_password(self, char_name):
        query = 'SELECT password from users where char_name = ?'
        return self.__dbpool.runQuery(query, [char_name])

    def is_char_online(self, char_name):
        query = 'SELECT online from users where char_name = ?'
        return self.__dbpool.runQuery(query, [char_name])

    def is_user_online(self, username):
        query = 'SELECT online from users where username = ?'
        return self.__dbpool.runQuery(query, [username])

    def does_char_name_exist(self, reg_char_exist):
        query = 'SELECT count(*) from users WHERE char_name = ?'
        return self.__dbpool.runQuery(query, [reg_char_exist])

    def get_mrpg_meta(self, name):
        query = 'SELECT value FROM mrpg_meta WHERE name = ?'
        return self.__dbpool.runQuery(query, (name))

    def is_user_admin(self, user):
        query = 'SELECT admin FROM users WHERE char_name = ? AND online = 1'
        return self.__dbpool.runQuery(query, [user])

    def make_user_online(self, username, hostname):
        query = 'UPDATE users SET online = 1, hostname = ? WHERE username = ?'
        return self.__dbpool.runQuery(query, (hostname,username))

    def make_user_offline(self, username, hostname):
        if hostname == "":
            query = 'UPDATE users SET online = 0 WHERE username = ?'
            return self.__dbpool.runQuery(query, [username])
        else:
            query = 'UPDATE users SET online = 0, hostname = ? WHERE username = ?'
            return self.__dbpool.runQuery(query, (hostname,username))

    def get_prefix(self, username):
        query = 'SELECT hostname FROM users WHERE username = ?'
        return self.__dbpool.runQuery(query, [username])

    def update_username(self, old_username, new_username, hostname):
        query = 'UPDATE users SET username = replace(username, ?, ?), hostname = ? where username = ?'
        return self.__dbpool.runQuery(query, (old_username, new_username, hostname, old_username))

    def get_event(self):
        limit = 1
        query = 'SELECT event_name, event_type, event_modifier FROM events ORDER BY RANDOM() LIMIT ?'
        return self.__dbpool.runQuery(query, [limit])

    def get_item(self):
        limit = 1
        query = '''SELECT t.item_description, i.item_name, i.modifier, i.special
                    FROM items i
                    INNER JOIN item_type t
                    ON i.item_type = t.id
                    ORDER BY RANDOM() LIMIT ?'''
        return self.__dbpool.runQuery(query, [limit])

    def get_random_user(self, limit):
        query = 'SELECT username FROM users WHERE online = 1 ORDER BY RANDOM() LIMIT ?'
        return self.__dbpool.runQuery(query, [limit])

    def get_user_ttl(self, user):
        query = 'SELECT ttl FROM users WHERE username = ?'
        return self.__dbpool.runQuery(query, [user])

    def get_program_meta(self, name):
        query = 'SELECT value FROM mrpg_meta WHERE name = ?'
        return self.__dbpool.runQuery(query, [name])

class Bot(irc.IRCClient):

    def privateMessage(self, user, msg):
        if self.factory.use_private_message == 1:
            self.msg(user, msg)
        else:
            self.notice(user, msg)

    def _get_nickname(self):
        return self.factory.nickname

    nickname = property(_get_nickname)

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.mrpg = mrpg(self)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)


    # callbacks for events

    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        self.join(self.factory.channel)
        self.nickservIdentify()
        #see comment below on def join()
        self.mrpg.start()

        #This was moved to signedOn so irc_JOIN works.
        # not sure if this will cause problems or not.
        #def joined(self, channel):
        #self.mrpg.start()

    def privmsg(self, user, channel, msg):
        hostname = user.split('~',1)[1]
        user = user.split('!', 1)[0]

        # Check to see if they're sending me a private message
        if channel == self.nickname:
            msg_split = msg.split(' ')
            msg_split[0] = msg_split[0].lower()
            lenow = len(msg_split)
            if (lenow == 1):
                options = {
                    'register' : 'To register: /msg ' + botname + ' register <char name> <password> <char class>',
                    'login': 'To login: /msg ' + botname + ' login <char name> <password>',
                    'logout': 'To logout: /msg ' + botname + ' logout <char name> <password>',
                    'newpass': 'To change your password: /msg ' + botname + ' NEWPASS <char name> <oldpass> <new password>',
                    'delete': 'To delete your account: /msg ' + botname + ' DELETE <char name> <password>',
                    'active': 'To see if you are currently logged in: /msg ' + botname + ' active <char name>',
                    'op': 'To op',
                    'help': 'Available commands: REGISTER, LOGIN, LOGOUT, NEWPASS, DELETE, ACTIVE, HELP'
                }
                if (options.has_key(msg_split[0])):
                    self.privateMessage(user,  options[msg_split[0]])
                else:
                    self.privateMessage(user, "Command not found. Try the help command.")
            else:
                @defer.inlineCallbacks
                def doregister():
                    if (lenow >= 4):
                        reg_char_name = msg_split[1]
                        reg_password = msg_split[2]
                        reg_char_class = msg_split[3::1]
                        reg_char_class = ' '.join(reg_char_class)

                        self.db = DBPool('mrpg.db')
                        char_exists = yield self.db.does_char_name_exist(reg_char_name)
                        self.db.shutdown("")
                        if(char_exists[0][0] == 1):
                            self.privateMessage(user, "There is already a character with that name.")
                        else:
                            hash = sc.encrypt(reg_password)
                            hash
                            '$6$rounds=36122$kzMjVFTjgSVuPoS.$zx2RoZ2TYRHoKn71Y60MFmyqNPxbNnTZdwYD8y2atgoRIp923WJSbcbQc6Af3osdW96MRfwb5Hk7FymOM6D7J1'
                            self.db = DBPool('mrpg.db')
                            self.db.register_char(user, reg_char_name, hash, reg_char_class, hostname)
                            query =      '''INSERT INTO items_user
                                                       (username
                                                       ,item_id
                                                       ,item_type
                                                       ,level
                                                       ,admin)
                                                 SELECT ?
                                                       ,(SELECT id
                                                           FROM items
                                                          WHERE item_type = t.id
                                                       ORDER BY RANDOM() LIMIT 1)
                                                       ,t.id
                                                       ,1
                                                       ,0
                                                   FROM item_type t'''
                            self.db.executeQuery(query,(user))
                            self.db.shutdown("")
                            self.privateMessage(user, "Created new character " + reg_char_name)
                            self.msg(self.mrpg.channel, "Welcome new character: " + reg_char_name + ", the " + reg_char_class)
                    else:
                        self.privateMessage(user, "Not enough information was supplied.")
                @defer.inlineCallbacks
                def dologin():
                    if (lenow >= 3):
                        login_char_name = msg_split[1]
                        login_password = msg_split[2]
                        self.db = DBPool('mrpg.db')
                        char_exists = yield self.db.does_char_name_exist(login_char_name)
                        self.db.shutdown("")
                        if(char_exists[0][0] == 0):
                            self.privateMessage(user, "There is not a character by that name.")
                        else:
                            self.db = DBPool('mrpg.db')
                            is_online = yield self.db.is_char_online(login_char_name)
                            self.db = DBPool('mrpg.db')
                            if (is_online[0][0] == 0):
                                self.db = DBPool('mrpg.db')
                                temppass = yield self.db.get_password(login_char_name)
                                passhash = temppass[0][0]
                                self.db.shutdown("")
                                if (sc.verify(login_password, passhash)):
                                    self.db = DBPool('mrpg.db')
                                    self.db.executeQuery("UPDATE users SET online = 1, hostname = ? WHERE char_name = ?",(hostname,login_char_name))
                                    self.db.shutdown("")
                                    self.mode(self.factory.channel, True, 'v', user=user)
                                    self.privateMessage(user, "You are now logged in.")
                                else:
                                    self.privateMessage(user, "Password incorrect.")
                            else:
                                self.privateMessage(user, "You are already logged in")
                    else:
                        self.privateMessage(user, "Not enough information was supplied.")

                @defer.inlineCallbacks
                def dologout():
                    if (lenow >= 3):
                        logout_char_name = msg_split[1]
                        logout_password = msg_split[2]
                        self.db = DBPool('mrpg.db')
                        char_exists = yield self.db.does_char_name_exist(logout_char_name)
                        self.db.shutdown("")
                        if(char_exists[0][0] == 0):
                            self.privateMessage(user, "There is not a character by that name.")
                        else:
                            self.db = DBPool('mrpg.db')
                            is_online = yield self.db.is_char_online(logout_char_name)
                            self.db.shutdown("")
                            if(is_online[0][0]==1):
                                self.db = DBPool('mrpg.db')
                                passhash = yield self.db.get_password(logout_char_name)
                                passhash = passhash[0][0]
                                self.db.shutdown("")
                                if (sc.verify(logout_password, passhash)):
                                    self.db = DBPool('mrpg.db')
                                    self.db.executeQuery("UPDATE users SET online = 0, hostname = ? WHERE char_name = ?",(hostname,logout_char_name))
                                    self.db.shutdown("")
                                    self.privateMessage(user, "You are now logged out.")
                                else:
                                    self.privateMessage(user, "Password incorrect.")
                            else:
                                self.privateMessage(user, "You are not logged in")
                    else:
                        self.privateMessage(user, "Not enough information was supplied.")

                @defer.inlineCallbacks
                def donewpass():
                    if (lenow >= 4):
                        newpass_char_name = msg_split[1]
                        newpass_password = msg_split[2]
                        newpass_new_password = msg_split[3]

                        self.db = DBPool('mrpg.db')
                        char_exists = yield self.db.does_char_name_exist(newpass_char_name)
                        self.db.shutdown("")
                        if(char_exists[0][0] == 0):
                            self.privateMessage(user, "There is not a character by that name.")
                        else:
                            self.db = DBPool('mrpg.db')
                            passhash = yield self.db.get_password(newpass_char_name)
                            passhash = passhash[0][0]
                            self.db.shutdown("")
                            if(sc.verify(newpass_password, passhash)):
                                hash = sc.encrypt(newpass_new_password)
                                hash
                                '$6$rounds=36122$kzMjVFTjgSVuPoS.$zx2RoZ2TYRHoKn71Y60MFmyqNPxbNnTZdwYD8y2atgoRIp923WJSbcbQc6Af3osdW96MRfwb5Hk7FymOM6D7J1'
                                self.db = DBPool('mrpg.db')
                                self.db.executeQuery("UPDATE users SET password = ? WHERE char_name = ?",(hash, newpass_char_name))
                                self.db.shutdown("")
                                self.privateMessage(user, "You have changed your password.")
                            else:
                                self.privateMessage(user, "Password incorrect.")
                    else:
                        self.privateMessage(user, "Not enough information was supplied.")

                @defer.inlineCallbacks
                def dodelete():
                    if (lenow >= 3):
                        delete_char_name = msg_split[1]
                        delete_password = msg_split[2]

                        self.db = DBPool('mrpg.db')
                        char_exists = yield self.db.does_char_name_exist(delete_char_name)
                        self.db.shutdown("")
                        if(char_exists[0][0] == 0):
                            self.privateMessage(user, "There is not a character by that name.")
                        else:
                            self.db = DBPool('mrpg.db')
                            passhash = yield self.db.get_password(delete_char_name)
                            passhash = passhash[0][0]
                            self.db.shutdown("")
                            if (sc.verify(delete_password, passhash)):
                                self.db = DBPool('mrpg.db')
                                self.db.executeQuery("DELETE FROM users WHERE char_name = ?",delete_char_name)
                                self.db.shutdown("")
                                self.privateMessage(user, delete_char_name + " has been deleted.")
                            else:
                                self.privateMessage(user, "Password incorrect.")
                    else:
                        self.privateMessage(user, "Not enough information was supplied.")

                @defer.inlineCallbacks
                def doactive():
                    active_char_name = msg_split[1]
                    self.db = DBPool('mrpg.db')
                    char_exists = yield self.db.does_char_name_exist(active_char_name)
                    if(char_exists[0][0] == 0):
                        self.privateMessage(user, "There is not a character by that name.")
                    else:
                        self.db = DBPool('mrpg.db')
                        char_online = yield self.db.executeQuery("SELECT online FROM users WHERE char_name = ?",active_char_name)
                        self.db.shutdown("")
                        if (char_online[0][0] == 0):
                            self.privateMessage(user, active_char_name + " is not online.")
                        else:
                            self.privateMessage(user, active_char_name + " is online.")


                def doop():
                    toop = msg_split[1]
                    #self.mode(self.factory.channel, True, 'o', user=toop)

                def dodeop():
                    toop = msg_split[1]
                    #self.mode(self.factory.channel, False, 'o', user=toop)

                @defer.inlineCallbacks
                def doinitialsetup():
                    toop = msg_split[1]

#                    self.db = DBPool('mrpg.db')
#                    value = "SUPERADMIN"
#                    a = yield self.db.executeQuery("SELECT value FROM mrpg_meta WHERE name = ?",value)
#
#                    if a:
#                        self.privateMessage(user, 'Initial setup has already been run. Your attempt to rerun setup has been logged.')
#                    else:
#                        yield self.db.executeQuery("UPDATE users SET admin = 1 WHERE char_name = ?", toop)
#                        yield self.db.executeQuery("INSERT INTO mrpg_meta VALUES('SUPERADMIN',?)" ,toop)
#
#                    self.db.shutdown("")


                def dohelp():
                    self.privateMessage(user, 'Available commands: REGISTER, LOGIN, LOGOUT, NEWPASS, DELETE, ACTIVE, HELP')
                    
                options = {
                    'register': doregister,
                    'login': dologin,
                    'logout': dologout,
                    'newpass': donewpass,
                    'delete': dodelete,
                    'active': doactive,
                    'op': doop,
                    'deop': dodeop,
                    'initialsetup': doinitialsetup,
                    'help': dohelp
                }
                if (options.has_key(msg_split[0])):
                    options[msg_split[0]]()
                else:
                    self.privateMessage(user, "Command not found. Try the help command.")
        else:
            self.mrpg.performPenalty(user, "channel message")

        # Otherwise check to see if it is a message directed at me
        if msg.startswith(self.nickname + ":"):
            msg_out = "%s: I am a log bot" % user
            self.msg(channel, msg_out)
            self.msg(channel, msg)
            if "shutdown" in msg:
                self.mrpg.stop()
            if "startup" in msg:
                self.mrpg.start()

    def action(self, user, channel, msg):
        user = user.split('!', 1)[0]
        self.mrpg.performPenalty(user, "Channel action")

    # irc callbacks

    def nickservRegister(self):
        self.msg("nickserv", "register " + self.factory.nickserv_password + " " + self.factory.nickserv_email)

    def nickservIdentify(self):
        self.msg("nickserv", "identify " + self.factory.nickserv_password)

    #THIS FUNCTION CAUSES joined() TO NOT WORK, SO ONLY USE ONE OR THE OTHER, NOT BOTH
    @defer.inlineCallbacks
    def irc_JOIN(self, prefix, params):
        #prefix ex. NeWtoz!~NeWtoz@2001:49f0:a000:n:jwn:tzoz:wuhi:zjhw
        #params ex. ['#xero']
        username = prefix.split('!',1)[0]
        hostname = prefix.split('~',1)[1]

        print "User: " + username + " with Host: " + hostname + " has joined the channel"
        #check username and hostname, and if match, log in.
        self.db = DBPool('mrpg.db')
        temp = yield self.db.get_prefix(username)
        #if multiple characters are allowed per username, goin to need a loop here
        if not temp:
            pass
        elif(temp[0][0] == hostname):
            self.db.make_user_online(username, hostname)
            self.mode(self.factory.channel, True, 'v', user=username)
            print "User: " + username + " with Host: " + hostname + " is being auto logged in"
        else:
            print "User: " + username + " with Host: " + hostname + " didn't qualify for auto login"
        self.db.shutdown("")

    @defer.inlineCallbacks
    def irc_PART(self, prefix, params):

        # Update the database

        username = prefix.split('!',1)[0]
        hostname = prefix.split('~',1)[1]

        # Assign the penalty
        self.mrpg.performPenalty(username, "Signed Off")

        print "User: " + username + " with Host: " + hostname + " has left the channel"
        self.db = DBPool('mrpg.db')
        is_online = yield self.db.is_user_online(username)
        db_prefix = yield self.db.get_prefix(username)
        if not is_online:
            pass
        elif(is_online[0][0] == 1 and db_prefix[0][0] == hostname):
            self.db.make_user_offline(username, hostname)
        self.db.shutdown("")

    @defer.inlineCallbacks
    def irc_QUIT(self, prefix, params):

        # Update the database
        username = prefix.split('!',1)[0]
        hostname = prefix.split('~',1)[1]

        # Assign the penalty
        self.mrpg.performPenalty(username, "Signed Off")

        print "User: " + username + " with Host: " + hostname + " has quit the server"
        self.db = DBPool('mrpg.db')
        is_online = yield self.db.is_user_online(username)
        db_prefix = yield self.db.get_prefix(username)
        if not is_online:
            pass
        elif(is_online[0][0] == 1 and db_prefix[0][0] == hostname):
            self.db.make_user_offline(username, hostname)
        self.db.shutdown("")

    @defer.inlineCallbacks
    def irc_KICK(self, prefix, params):
        #kicker = prefix
        kickee = params[1]

        self.mrpg.performPenalty(kickee, "Kicked")
        self.db = DBPool('mrpg.db')
        is_online = yield self.db.is_user_online(kickee)
        if not is_online:
            pass
        elif(is_online[0][0] == 1):
            self.db.make_user_offline(kickee, "")
        self.db.shutdown("")

    @defer.inlineCallbacks
    def irc_NICK(self, prefix, params):
        # Update the database with the new username information
        old_username = prefix.split('!',1)[0]
        hostname = prefix.split('~',1)[1]
        new_username = params[0]
        print "User: " + old_username + " with Host: " + hostname + " has changed their name to " + new_username
        self.db = DBPool('mrpg.db')
        is_online = yield self.db.is_user_online(old_username)
        db_prefix = yield self.db.get_prefix(old_username)
        if not is_online:
            pass
        elif(is_online[0][0] == 1 and db_prefix[0][0] == hostname):
            self.db.update_username(old_username, new_username, hostname)
        self.db.shutdown("")

        # Assign penalty
        self.mrpg.performPenalty(new_username, "Changed nickname")

class BotFactory(protocol.ClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    def __init__(self):
        config = ConfigParser.RawConfigParser()
        config.read('config.cfg')

        channel = config.get('IRC', 'channel')
        nickname = config.get('IRC', 'nickname')

        self.channel = config.get('IRC', 'channel')
        self.nickname = config.get('IRC', 'nickname')
        self.nickserv_password = config.get('IRC', 'nickserv_password')
        self.nickserv_email = config.get('IRC', 'nickserv_email')
        self.use_private_message = config.getint('BOT', 'use_private_message')
        self.event_randomness = config.getint('BOT','event_randomness')
        self.item_randomness = config.getint('BOT','item_randomness')

    def buildProtocol(self, addr):
        p = Bot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "connection failed:", reason
        reactor.stop()

if __name__ == '__main__':
    # initialize logging
    log.startLogging(sys.stdout)

    con = lite.connect('mrpg.db')
    with con:
        cur = con.cursor()
        cur.execute("SELECT value FROM mrpg_meta WHERE name = 'VERSION'")
        version = cur.fetchone()
        if float(version[0]) < min_schema_ver_needed:
            for x in range(0,20):
                print "Your DB version is out of date. Please upgrade."
            sys.exit("Shutting down")
        else:
            print "Your DB version is compatible. Continuing to load."

            config = ConfigParser.RawConfigParser()
            config.read('config.cfg')

            server = config.get('IRC', 'server')
            port = config.getint('IRC', 'port')
            botname = config.get('IRC', 'nickname')
            timespan = config.getfloat('BOT', 'timespan')
            min_time = config.getint('BOT', 'min_time')
            penalty_constant = config.getfloat('BOT', 'penalty_constant')
            movespan = config.getfloat('MOV', 'movespan')
            world_radius = config.getfloat('MOV', 'world_radius')
            walking_speed = config.getfloat('MOV', 'walking_speed')
            # create factory protocol and application
            f = BotFactory()

            # connect factory to this host and port
            reactor.connectTCP(server, port, f)

            # run bot
            reactor.run()