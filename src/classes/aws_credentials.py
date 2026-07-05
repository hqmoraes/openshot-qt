"""
 @file
 @brief Builds AWS/boto3 sessions from user-configurable Preferences settings.

 No AWS credentials are ever hard-coded in this file. All values (auth mode,
 access key, secret key, session token, profile name, region, and the
 AgentCore harness/agent ARN) are read from the user's local OpenShot
 settings store (populated through the Preferences dialog), so this code can
 be freely distributed and reused with any AWS account.

 @section LICENSE

 Copyright (c) 2008-2026 OpenShot Studios, LLC
 (http://www.openshotstudios.com). This file is part of
 OpenShot Video Editor (http://www.openshot.org), an open-source project
 dedicated to delivering high quality video editing and animation solutions
 to the world.

 OpenShot Video Editor is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 OpenShot Video Editor is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with OpenShot Library.  If not, see <http://www.gnu.org/licenses/>.
"""

from classes.app import get_app
from classes.logger import log


class AwsCredentialsError(Exception):
    """Raised when AWS credentials/settings are missing, invalid, or boto3
    is not installed."""


def get_aws_settings():
    """Read the AI Agent settings block from the user's local settings store."""
    s = get_app().get_settings()
    return {
        "enabled": bool(s.get("aws-agent-enabled")),
        "auth_mode": str(s.get("aws-auth-mode") or "default_chain"),
        "profile_name": str(s.get("aws-profile-name") or "").strip(),
        "access_key_id": str(s.get("aws-access-key-id") or "").strip(),
        "secret_access_key": str(s.get("aws-secret-access-key") or "").strip(),
        "session_token": str(s.get("aws-session-token") or "").strip(),
        "region": str(s.get("aws-region") or "").strip() or "us-east-1",
        "harness_arn": str(s.get("agentcore-harness-arn") or "").strip(),
    }


def build_boto3_session(settings=None):
    """Build a boto3.Session using the user's configured auth mode.

    Raises AwsCredentialsError if boto3 isn't installed or required
    settings are missing.
    """
    try:
        import boto3
    except ImportError as ex:
        raise AwsCredentialsError(
            "The 'boto3' package is required for AWS/AgentCore features. "
            "Install it with: pip install boto3"
        ) from ex

    cfg = settings or get_aws_settings()
    auth_mode = cfg["auth_mode"]

    if auth_mode == "access_keys":
        if not cfg["access_key_id"] or not cfg["secret_access_key"]:
            raise AwsCredentialsError(
                "AWS Access Key ID and Secret Access Key are required for "
                "the 'Access Key / Secret Key' authentication method."
            )
        return boto3.Session(
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
            aws_session_token=cfg["session_token"] or None,
            region_name=cfg["region"],
        )

    if auth_mode == "profile":
        if not cfg["profile_name"]:
            raise AwsCredentialsError(
                "An AWS Profile Name is required for the 'Named AWS Profile' "
                "authentication method."
            )
        return boto3.Session(profile_name=cfg["profile_name"], region_name=cfg["region"])

    # default_chain: environment variables, shared credentials file, IAM role, SSO, etc.
    return boto3.Session(region_name=cfg["region"])


def test_connection(settings=None, timeout=5.0):
    """Validate AWS credentials by calling STS GetCallerIdentity.

    Returns a tuple: (success: bool, message: str).
    Never raises - all errors are captured and returned as a message.
    """
    try:
        from botocore.config import Config
    except ImportError:
        return False, "The 'boto3'/'botocore' package is required. Install it with: pip install boto3"

    try:
        session = build_boto3_session(settings)
        client = session.client(
            "sts",
            config=Config(connect_timeout=timeout, read_timeout=timeout, retries={"max_attempts": 1}),
        )
        identity = client.get_caller_identity()
        account = identity.get("Account", "?")
        arn = identity.get("Arn", "?")
        return True, "Connected as {} (account {})".format(arn, account)
    except AwsCredentialsError as ex:
        return False, str(ex)
    except Exception as ex:
        log.warning("AWS connection test failed: %s", ex)
        return False, str(ex)
