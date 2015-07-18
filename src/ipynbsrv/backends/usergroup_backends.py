from ipynbsrv.contract.backends import GroupBackend, UserBackend
from ipynbsrv.contract.errors import *
import ldap


class LdapBackend(GroupBackend, UserBackend):

    """
    Group- and UserBackend implementation communicating with an LDAP server.

    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library
    """

    def __init__(self, server, base_dn, users_dn=None, groups_dn=None, readonly=False):
        """

        """
        if "ldap://" not in server:
            server = "ldap://" + server

        self.base_dn = base_dn
        self.groups_dn = groups_dn
        self.readonly = readonly
        self.server = server
        self.users_dn = users_dn

    def add_group_member(self, group, user, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.group_exists(group):
            raise GroupNotFoundError
        if not self.user_exists(user):
            raise UserNotFoundError

        dn = self.get_full_group_dn(group)
        mod_attrs = [
            (ldap.MOD_ADD, 'memberUid', [user])
        ]
        try:
            self.cnx.modify_s(dn, mod_attrs)
        except Exception as ex:
            raise GroupBackendError(ex)

    def auth_user(self, user, credential, **kwargs):
        """
        :inherit.
        """
        if not self.user_exists(user):
            raise UserNotFoundError

        try:
            user_ldap = LdapBackend(self.server, self.base_dn, self.users_dn)
            user_ldap.connect({
                'dn': self.get_full_user_dn(user),
                'password': credential
            })
            user_ldap.disconnect()
            return self.get_user(user)
        except ldap.INVALID_CREDENTIALS as ex:
            raise AuthenticationError(ex)
        except ldap.LDAPError as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def connect(self, credentials, **kwargs):
        """
        :inherit.
        """
        dn = credentials.get('dn')
        if dn is None:
            username = credentials.get('username')
        else:
            username = dn

        try:
            self.cnx = ldap.initialize(self.server)
            self.cnx.bind_s(username, credentials.get('password'))
        except ldap.INVALID_CREDENTIALS as ex:
            raise AuthenticationError(ex)
        except ldap.LDAPError as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def create_group(self, specification, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        self.validate_group_creation_specification(specification)
        # TODO: check if such a group already exists

        name = specification.get('name')
        gid = specification.get('gidNumber')
        record = [
            ('objectclass', [
                'posixGroup',
                'top'
            ]),
            ('cn', [name]),
            ('gidNumber', [str(gid)]),
            ('memberUid', [memberUid])  # FIXME: hmm..
        ]
        dn = self.get_full_group_dn(name)
        try:
            self.cnx.add_s(dn, record)
            group = {}
            # TODO: add more fields
            group[GroupBackend.FIELD_ID] = gid
            group[GroupBackend.FIELD_PK] = name
            return group
        except Exception as ex:
            raise GroupBackendError(ex)

    def create_user(self, specification, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        self.validate_user_creation_specification(specification)
        # TODO: check if such a user already exists

        username = specification.get('username')
        uid = specification.get('uidNumber')
        dn = self.get_full_user_dn(username)
        record = [
            ('objectclass', [
                'person',
                'organizationalperson',
                'inetorgperson',
                'posixAccount',
                'top'
            ]),
            ('cn', [username]),
            ('sn', [username]),
            ('uid', [username]),
            ('uidNumber', [str(uid)]),
            ('gidNumber', [str(specification.get('gidNumber'))]),  # FIXME: hmm..
            ('userpassword', [specification.get('password')]),
            ('homedirectory', [specification.get('homeDirectory')])
        ]
        try:
            self.cnx.add_s(dn, record)
            user = {}
            # TODO: add more fields
            user[UserBackend.FIELD_ID] = uid
            user[UserBackend.FIELD_PK] = username
            return user
        except Exception as ex:
            raise UserBackendError(ex)

    def delete_group(self, group, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.group_exist(group):
            raise GroupNotFoundError

        dn = self.get_full_group_dn(group)
        try:
            self.cnx.delete_s(dn)
        except ldap.NO_SUCH_OBJECT as ex:
            raise GroupNotFoundError(ex)
        except Exception as ex:
            raise GroupBackendError(ex)

    def delete_user(self, user, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.user_exists(user):
            raise UserNotFoundError

        dn = self.get_full_user_dn(user)
        try:
            self.cnx.delete_s(dn)
        except ldap.NO_SUCH_OBJECT as ex:
            raise UserNotFoundError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def disconnect(self, **kwargs):
        """
        :inherit.
        """
        try:
            self.cnx.unbind_s()
        except ldap.LDAPError as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def get_full_dn(self, cn):
        """
        TODO: write doc.
        """
        return "%s,%s" % (cn, self.base_dn)

    def get_full_group_dn(self, group):
        """
        TODO: write doc.
        """
        return self.get_full_dn("cn=%s,%s" % (group, self.groups_dn))

    def get_full_user_dn(self, user):
        """
        TODO: write doc.
        """
        return self.get_full_dn("cn=%s,%s" % (user, self.users_dn))

    def get_required_group_creation_fields(self):
        """
        :inherit.
        """
        return [
            ('groupname', str),
            ('gidNumber', int),
            ('memberUid', str)
        ]

    def get_required_user_creation_fields(self):
        """
        :inherit.
        """
        return [
            ('username', str),
            ('uidNumber', int),
            ('gidNumber', int),
            ('password', str),
            ('homeDirectory', str)
        ]

    def get_group(self, group, **kwargs):
        """
        :inherit.
        """
        if not self.group_exists(group):
            raise GroupNotFoundError

        base = self.get_full_dn(self.groups_dn)
        scope = ldap.SCOPE_SUBTREE
        s_filter = 'cn=' + group
        result = None
        try:
            result = self.cnx.search_s(base, scope, filterstr=s_filter)
        except ldap.NO_SUCH_OBJECT as ex:
            raise GroupNotFoundError(ex)
        except Exception as ex:
            raise GroupBackendError(ex)

        matches = len(result)
        if matches == 0:
            raise GroupNotFoundError
        elif matches != 1:
            raise GroupBackendError("Multiple groups found")
        else:
            group = result[0][1]
            group[UserBackend.FIELD_ID] = int(group.get('gidNumber')[0])
            group[UserBackend.FIELD_PK] = group.get('cn')[0]
            return group

    def get_group_members(self, group, **kwargs):
        if not self.group_exists(group):
            raise GroupNotFoundError

        group = None
        dn = self.get_full_group_dn(group)
        try:
            group = self.cnx.read_s(dn)
        except ldap.NO_SUCH_OBJECT as ex:
            raise GroupNotFoundError(ex)
        except Exception as ex:
            raise GroupBackendError(ex)

        if group is None or 'memberUid' not in group:
            return []
        else:
            users = []
            for user in group.get('memberUid'):
                users += self.get_user(user)
            return users

    def get_groups(self, **kwargs):
        """
        :inherit.
        """
        base = self.get_full_dn(self.groups_dn)
        scope = ldap.SCOPE_ONELEVEL
        try:
            # get list of groups and remove dn, to only have dicts in the list
            # lda.SCOPE_ONELEVEL == 1, search only childs of dn
            groups = map(lambda x: x[1], self.cnx.search_s(base, scope))
            for group in groups:
                group[UserBackend.FIELD_ID] = int(group.get('gidNumber')[0])
                group[UserBackend.FIELD_PK] = group.get('cn')[0]
            return groups
        except Exception as e:
            raise GroupBackendError(e)

    def get_user(self, user, **kwargs):
        """
        :inherit.
        """
        if not self.user_exists(user):
            raise UserNotFoundError

        base = self.get_full_dn(self.users_dn)
        scope = ldap.SCOPE_SUBTREE
        s_filter = 'cn=' + user
        result = None
        try:
            result = self.cnx.search_s(base, scope, filterstr=s_filter)
        except ldap.NO_SUCH_OBJECT as ex:
            raise UserNotFoundError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

        matches = len(result)
        if matches == 0:
            raise UserNotFoundError
        elif matches != 1:
            raise UserBackendError("Multiple users found")
        else:
            user = result[0][1]
            user[UserBackend.FIELD_ID] = int(user.get('uidNumber')[0])
            user[UserBackend.FIELD_PK] = user.get('cn')[0]
            return user

    def get_users(self, **kwargs):
        """
        :inherit.
        """
        base = self.get_full_dn(self.users_dn)
        scope = ldap.SCOPE_ONELEVEL
        try:
            # get list of users and remove dn, to only have dicts in the list
            # lda.SCOPE_ONELEVEL == 1, search only childs of dn
            users = map(lambda x: x[1], self.cnx.search_s(base, scope))
            for user in users:
                user[UserBackend.FIELD_ID] = int(user.get('uidNumber')[0])
                user[UserBackend.FIELD_PK] = user.get('cn')[0]
            return users
        except Exception as e:
            raise UserBackendError(e)

    def group_exists(self, group):
        """
        :inherit.
        """
        base = self.get_full_dn(self.groups_dn)
        scope = ldap.SCOPE_SUBTREE
        s_filter = 'cn=' + group
        result = None
        try:
            result = self.cnx.search_s(base, scope, filterstr=s_filter)
            return len(result) != 0
        except ldap.NO_SUCH_OBJECT as ex:
            return False
        except Exception as ex:
            raise GroupBackendError(ex)

    def remove_group_member(self, group, user, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.group_exist(group):
            raise GroupNotFoundError
        if not self.user_exists(user):
            raise UserNotFoundError

        dn = self.get_full_group_dn(group)
        mod_attrs = [
            (ldap.MOD_DELETE, 'memberUid', [user])
        ]
        try:
            self.cnx.modify_s(dn, mod_attrs)
        except Exception as ex:
            raise GroupBackendError(ex)

    def rename_group(self, group, new_name, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.group_exists(group):
            raise GroupNotFoundError

        dn = self.get_full_group_dn(group)
        try:
            # TODO: update memberUid gidNumbers
            # copy object to new dn and delete old one
            self.cnx.modrdn_s(dn, "cn={0}".format(new_name), delold=1)
        except ldap.NO_SUCH_OBJECT as ex:
            raise GroupNotFoundError(ex)
        except Exception as ex:
            raise GroupBackendError(ex)

    def rename_user(self, user, new_name, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.user_exists(user):
            raise UserNotFoundError

        dn = self.get_full_user_dn(user)
        mod_attrs = [
            (ldap.MOD_REPLACE, 'uid', new_name),
            (ldap.MOD_REPLACE, 'sn', new_name)
        ]
        try:
            # TODO: update groups memberUids
            # first: change name fields
            self.cnx.modify_s(dn, mod_attrs)
            # then: copy object to new dn and delete old one
            self.cnx.modrdn_s(dn, "cn={0}".format(new_name), delold=1)
        except ldap.NO_SUCH_OBJECT as ex:
            raise UserNotFoundError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def set_user_credential(self, user, credential, **kwargs):
        """
        :inherit.
        """
        if self.readonly:
            raise ReadOnlyError
        if not self.user_exists(user):
            raise UserNotFoundError

        dn = self.get_full_user_dn(user)
        mod_attrs = [
            (ldap.MOD_REPLACE, 'userpassword', password)
        ]
        try:
            self.cnx.modify_s(dn, mod_attrs)
        except ldap.NO_SUCH_OBJECT as ex:
            raise UserNotFoundError(ex)
        except Exception as ex:
            raise UserBackendError(ex)

    def user_exists(self, user):
        """
        :inherit.
        """
        base = self.get_full_dn(self.users_dn)
        scope = ldap.SCOPE_SUBTREE
        s_filter = 'cn=' + user
        try:
            result = self.cnx.search_s(base, scope, filterstr=s_filter)
            return len(result) != 0
        except ldap.NO_SUCH_OBJECT as ex:
            return False
        except Exception as ex:
            raise UserBackendError(ex)

    def validate_group_creation_specification(self, specification):
        """
        Validate that the specification matches the definition.

        :param specification: The specification to validate.
        """
        for rname, rtype in self.get_required_group_creation_fields():
            field = specification.get(rname)
            # TODO: raise errors
            if field is None:
                pass
            elif not isinstance(field, rtype):
                pass

    def validate_user_creation_specification(self, specification):
        """
        Validate that the specification matches the definition.

        :param specification: The specification to validate.
        """
        for rname, rtype in self.get_required_user_creation_fields():
            field = specification.get(rname)
            # TODO: raise errors
            if field is None:
                pass
            elif not isinstance(field, rtype):
                pass
