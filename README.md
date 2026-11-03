pycharm-community-edition
=========================

## COPR fork

This fork builds `pycharm-community` 2026.2.4 for x86_64 on Fedora 43, 44,
45, and Rawhide in `ok8219/PyCharm`. It retains the upstream bundled JetBrains
Runtime `25.0.4.1+1-b508.41`, which JetBrains identifies as fixed for the
[eMudhra certificate incident](https://blog.jetbrains.com/security/2026/10/compromised-emudhra-certificates-ides/).
The bundled runtime is not OpenJDK 27. The separate plugins package is not
built by this fork's workflow; an installed plugins package requiring an older
PyCharm version may prevent upgrading until it is updated or removed.

The embedded browser needs to reach Google's update servers to obtain its own
certificate updates; see the JetBrains advisory for details and workarounds.

[![PyCharm build status](https://copr.fedorainfracloud.org/coprs/phracek/PyCharm/package/pycharm-community/status_image/last_build.png)](https://copr.fedorainfracloud.org/coprs/phracek/PyCharm/package/pycharm-community/)
[![Plugins build status](https://copr.fedorainfracloud.org/coprs/phracek/PyCharm/package/pycharm-community-plugins/status_image/last_build.png)](https://copr.fedorainfracloud.org/coprs/phracek/PyCharm/package/pycharm-community-plugins/)

PyCharm Community Edition IDE editor for developing not only python applications.

This GIT repository contains files necessary for building RPMs for Fedora/RHEL.

You only need to download sources from www.jetbrains.com/pycharm
