# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r"""
attributes:
  check_mode:
    description: Can run in check mode and return the changed status without changing anything.
  diff_mode:
    description: Will return details on what changed (or would change) in diff mode.
"""
