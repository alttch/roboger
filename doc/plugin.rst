Plugin development
******************

Plugin Python module should be called as *robogercontrib.modulename* and be
available to import.

Optional methods can be absent. When called, method can raise an exception,
which will be logged, when server is in debug mode.

Methods
=======

.. important::
   
   All plugin methods should end with \*\*kwargs to let core send additional
   parameters in the future.

send
----

Plugin module SHOULD implement at least *send* method, which is called when
configured endpoint receives an event, and gets the following data in kwargs:

* **config** dict with endpoint configuration
* **event_id** event unique id (UUID, string)
* **addr** event address on Roboger server
* **addr_id** event address ID on Roboger server
* **msg** message text
* **subject** message subject
* **formatted_subject** pre-formatted subject with level and location
* **level** event level (integer)
* **level_name** event level (string)
* **location** event location
* **tag** event tag
* **media** event media, binary
* **media_encoded** event media, base64-encoded
* **media_fname** event media file name, if specified by sender

validate_config
---------------

Optional, called when core asks plugin to validate endpoint configuration.
Usually should implement JSON schema validation + any additional, if required.

e.g.

.. code:: python

   def validate_config(config, **kwargs):
      jsonschema.validate(config, SOME_SCHEMA)

validate_plugin_config
----------------------

Optional, called before plugin loading, core asks plugin to validate its global
configuration. Usually should implement JSON schema validation + any
additional, if required. If plugin has no configuration options, it should
raise *ValueError* exception in case if plugin_config is not empty.

e.g.

.. code:: python

   def validate_plugin_config(plugin_config, **kwargs):
      jsonschema.validate(plugin_config, SOME_SCHEMA)

load
----

Optional, called on core load, params:

* **plugin_config** contains dict with plugin configuration, specified in
  Roboger server main configuration file.

This method initializes plugin global parameters, if required.

cleanup
-------

Optional, called when core cleanup is requested.

This method should clean any temporary/expired files and database entries, if
the plugin creates some.

Logging
=======

The plugin should import logger and *log_traceback* method from Roboger core
and use them for logging, specifying __name__ at start of the string:

.. code:: python

   from roboger.core import logger, log_traceback

   logger.debug(f'{__name__} will do something')
   try:
      break_something()
   except Exception as e:
      logger.debug(f'{__name__} oops, error: {e}')
      log_traceback()

Additional core methods
=======================

The following additional *roboger.core* methods may be useful for plugins:

* **get_db_engine()** get database engine (SQLAlchemy)

* **get_db()** get database connection (thread-local)

* **spawn(method, \*args, \*\*kwargs)** submit function to core thread-pool

* **get_app()** get core web application. If plugin want to have own HTTP
  methods, they SHOULD have URI: */plugin/{plugin_name}/whatever_you_want*

* **get_timeout()** get default timeout

* **get_real_ip()** get IP address of current API call

* **get_plugin(plugin_name)** get another plugin module

* **convert_level(level)** convert event level to integer code

* **is_use_lastrowid()** should *lastrowid* be used for the database queries (if not - database supports *RETURNING*)

* **is_use_limits()** is Roboger server configured to have limits applied on addresses or not.

Bucket
======

Roboger provides storage bucket for plugins to temporary store media and other
files (e.g. allow user open media file via link).

Methods
-------

Bucket objects are managed by *roboger.core* methods, which can be imported
into your plugin (see function pydoc for arguments etc.):

* **bucket_put** create object
* **bucket_get** get object
* **bucket_touch** set object access time to current
* **bucket_delete** delete object

Features and rules
------------------

* Object ID is SHA256 hash of first 1024 bytes of object content, current time,
  creator and address id.

* When creating bucket object, set *creator* attribute to
  *plugin.{yourpluginname}*

* If created with *public=True*, bucket object can be accessed at
  */file/{object_id}*. Other objects are not accessible with HTTP API (unless
  provided by plugin)

* Bucket object can not be modified after creation.

* Bucket object is not accessible (including core bucket_get function) after
  the expiration. Expiration time is calculated from object creation, lifetime
  can not be extended.
