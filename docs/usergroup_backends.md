# Group/User Backends

> Official `ipynbsrv.contract.backends.GroupBackend` and `ipynbsrv.contract.backends.UserBackend` implementations from the core developers.

## LdapBackend

The *Lightweight Directory Access Protocol* is a widly supported protocol to communicate with directory servers like Window's Active Directory. The `LdapBackend` implements the `GroupBackend` and `UserBackend` contracts to use such a directory service as an `ipynbsrv` backend. It can be used to allow users on an existing directory service to login to the application. Under the hood, the `python-ldap` package is used.

This backend is also used for the internally used LDAP server, on which user accounts and groups are stored (so the application doesn't have to rely on the external backend).

### Reusing the internal LDAP server

For the case no external directory service exist, the internal LDAP server can be used to simulate one. This has the benefit that no extra server needs to be setup, because the internal one exists anyway. Only a few additional steps are required compared to the regular setup.

#### Creating the LDAP users unit

The internal LDAP server uses the `groups` and `users` organizational units to store records. To simulate an external source, an additional OU needs to be defined.

This can be done either through a desktop application or the command-line (like in the main install guide).

The easiest way is to enter the internal LDAP container with:

```bash
docker enter ipynbsrv_ldap
```

> This only works if the core infrastructure is running on Docker (which is the default).

And create a temporary file named `_users.ldif` with the following content:

```
dn: ou=_users,dc=ipynbsrv,dc=ldap
changetype: add
objectclass: organizationalUnit
objectclass: top
ou: _users
```

Using the LDAP server's administration tools, these instructions can be transfered to the server, which will setup the OU:

```bash
ldapadd -h localhost -p 389 -c -x -D cn=admin,dc=ipynbsrv,dc=ldap -W -f _users.ldif
```

> You'll be prompted to enter a password. It is the LDAP admin password you defined during the LDAP container bootstrap process.

#### Managing user accounts

TODO 