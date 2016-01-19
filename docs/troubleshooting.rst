Troubleshooting
===============


These are the recommended steps to follow if you run into any issues using
Mopidy-Pandora.

Check the logs
--------------

Have a look at the contents of ``mopidy.log`` to see if there are any obvious
issues that require attention. This could range from ``mopidy.conf`` parsing
errors, or problems with the Pandora account that you are using.

Ensure that Mopidy is running
-----------------------------

Make sure that Mopidy itself is working correctly and that it is accessible
via the browser. Disable the Mopidy-Pandora extension by setting
``enabled = false`` in the ``pandora`` section of your configuration file,
restart Mopidy, and confirm that the other Mopidy extensions that you have
installed work as expected.

Ensure that you are connected to the internet
---------------------------------------------

This sounds rather obvious but Mopidy-Pandora relies on a working internet
connection to log on to the Pandora servers and retrieve station information.
If you are behind a proxy, you may have to configure some of Mopidy's
`proxy settings <http://mopidy.readthedocs.org/en/latest/config/?highlight=proxy#proxy-configuration>`_.

Run pydora directly
-------------------

Mopidy-Pandora makes use of the pydora API, which comes bundled with its own
command-line player that can be run completely independently of Mopidy. This
is often useful for isolating issues to determine if they are Mopidy related,
or due to problems with your Pandora user account or any of a range of
technical issues in reaching and logging in to the Pandora servers.

Follow the `installation instructions <https://github.com/mcrute/pydora#installing>`_
and use ``pydora-configure`` to create the necessary configuration file in
``~/.pydora.cfg``. Once that is done running ``pydora`` from the command line will
give you a quick indication of whether the issues are Mopidy-specific or not.

Try a different Pandora user account
------------------------------------

It sometimes happens that Pandora will temporarily block a user account if you
exceed any of the internal skip or station request limits. It may be a good
idea to register a separate free account at `www.pandora.com <www.pandora.com>`_
for testing - just to make sure that the problem is not somehow related to an
issue with your primary Pandora user account.
