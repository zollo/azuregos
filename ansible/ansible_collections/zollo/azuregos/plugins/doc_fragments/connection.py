# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):
    # How every zollo.azuregos module reaches and signs in to the API.
    DOCUMENTATION = r"""
options:
  api_url:
    description:
      - Base URL of the Azuregos instance, for example V(https://azuregos.example.com).
      - The modules call C(<api_url>/api/...).
      - If not set, the E(AZUREGOS_URL) environment variable is used.
    type: str
    required: true
  api_token:
    description:
      - API bearer token (the JWT the API returns from C(POST /api/auth/login)).
      - Takes precedence over O(api_username) and O(api_password).
      - If not set, the E(AZUREGOS_TOKEN) environment variable is used.
    type: str
  api_username:
    description:
      - Email of a local account to sign in with when O(api_token) isn't set.
      - If not set, the E(AZUREGOS_USERNAME) environment variable is used.
    type: str
  api_password:
    description:
      - Password of O(api_username).
      - If not set, the E(AZUREGOS_PASSWORD) environment variable is used.
    type: str
  validate_certs:
    description:
      - Whether to verify the server's TLS certificate.
      - If not set, the E(AZUREGOS_VALIDATE_CERTS) environment variable is used.
    type: bool
    default: true
  api_timeout:
    description:
      - Seconds to wait for each API request.
    type: int
    default: 30
notes:
  - "Set the connection options once for a play with C(module_defaults) and the
    C(group/zollo.azuregos.all) action group."
"""
