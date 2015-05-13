from ipynbsrv.contract.backends import UserGroupBackend
import ldap
import sys


class Ldap(UserGroupBackend):
    '''
    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library

    tested:
        create_user
        create_group
        delete_user
        delete_group
        rename_user
        rename_group

    '''

    def __init__(self, ldap_server, admin_dn, admin_pw,
                 user_base_dn='ou=users,dc=ipynbsrv,dc=ldap',
                 group_base_dn='ou=groups,dc=ipynbsrv,dc=ldap'
                 ):
        '''
        Create a Ldap Connector

        Args:
            ldap_server:    Hostname or IP of the LDAP server           
            admin_dn:       dn of the LDAP admin user
            admin_pw:       admin password
            user_base_dn:   Base DN for users (default: ou=users,dc=ipynbsrv,dc=ldap)
            group_base_dn:  Base DN for groups (default: ou=groups,dc=ipynbsrv,dc=ldap)
        '''
        if not "ldap://" in ldap_server:
            ldap_server = "ldap://" + ldap_server
        self.ldap_server = ldap_server
        self.server = ldap_server
        self.admin_dn = admin_dn
        self.admin_pw = admin_pw
        self.user_base_dn = user_base_dn
        self.group_base_dn = group_base_dn

    ''' Helper Functions ------------------------------------ '''

    def open_connection(self):
        try:
            self.conn = ldap.initialize(self.server)
            self.conn.bind_s(self.admin_dn, self.admin_pw)
        except ldap.INVALID_CREDENTIALS:
            print("Your username or password is incorrect.")
            sys.exit()
        except ldap.LDAPError as e:
            if type(e.message) == dict and 'desc' in e.message:
                print(e.message['desc'])
            else:
                print(e)
            sys.exit()

    def close_connection(self):
        try:
            self.conn.unbind()
        except Exception as e:
            print("Problem closing connection")
            if type(e.message) == dict and 'desc' in e.message:
                print(e.message['desc'])
            else:
                print(e)
            sys.exit()

    def get_dn_by_username(self, username):
        return "cn={0},{1}".format(username, self.user_base_dn)

    def get_dn_by_groupname(self, groupname):
        return "cn={0},{1}".format(groupname, self.group_base_dn)


    ''' User Functions ------------------------------------ '''

    def create_user(self, username, password):
        '''
        Creates LDAP user on the server

        Args:

            username:   name of the user to create
            password:   password for the new user

        Returns:

        Raises:

        Todo:
            Homedir in parameters?
        '''

        if type(username) is not str or type(password) is not str:
            raise ValueError("Username and Password must be strings")

        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)

            add_record = [
                ('objectclass', ['person', 'organizationalperson', 'inetorgperson', 'posixAccount', 'top']),
                ('uid', [username]),
                ('uidNumber', ['2500']),
                ('gidNumber', ['2500']),
                ('cn', [username]),
                ('sn', [username]),
                ('userpassword', [password]),
                ('homedirectory', ['/home/test'])
            ]
            self.conn.add_s(dn, add_record)
        finally:
            self.close_connection()

    def rename_user(self, username, username_new):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)

            # First: change name fields
            mod_attrs = [(ldap.MOD_REPLACE, 'uid', username_new),
                         (ldap.MOD_REPLACE, 'sn', username_new)
                         ]
            self.conn.modify_s(dn, mod_attrs)

            # Then: copy object to new dn and delete old one
            self.conn.modrdn_s(dn, "cn={0}".format(username_new), delold=1)

        finally:
            self.close_connection()

    def set_user_password(self, username, new_pw):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)
            mod_attrs = [(ldap.MOD_REPLACE, 'userpassword', new_pw)]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def delete_user(self, username):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)
            self.conn.delete(dn)
        finally:
            self.close_connection()

    def add_user_to_group(self, username, gid):
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_username(username)
            mod_attrs = [(ldap.MOD_ADD, 'gidNumber', [gid])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def remove_user_from_group(self, username, gid):
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_username(username)
            mod_attrs = [(ldap.MOD_DELETE, 'gidNumber', [gid])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    ''' Group Functions ------------------------------------ '''

    def create_group(self, groupname):
        if type(groupname) is not str:
            raise ValueError("Groupname must be a string")

        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            add_record = [
                ('objectclass', ['posixGroup', 'top']),
                ('gidNumber', ['2500']),  # Where does this come from?
                ('cn', [groupname]),
                ('memberUid', '')  # TODO: What goes here?
            ]
            self.conn.add_s(dn, add_record)
        finally:
            self.close_connection()

    def rename_group(self, groupname, groupname_new):
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            # copy object to new dn and delete old one
            self.conn.modrdn_s(dn, "cn={0}".format(groupname_new), delold=1)

        finally:
            self.close_connection()

    def delete_group(self, groupname):
        # TODO: what to do with users in that group?
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)
            self.conn.delete(dn)
        finally:
            self.close_connection()
