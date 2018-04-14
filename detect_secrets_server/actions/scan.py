from detect_secrets.core.log import CustomLog

from detect_secrets_server.repos.base_tracked_repo import OverrideLevel
from detect_secrets_server.repos.factory import tracked_repo_factory
from detect_secrets_server.repos.s3_tracked_repo import S3Config


def scan_repo(args):
    """Returns 0 on success"""
    repo = tracked_repo_factory(
        args.local,
        bool(args.s3_config_file),
    ).load_from_file(
        args.scan_repo[0],
        args.base_temp_dir[0],
        S3Config(**args.s3_config_file),
    )

    if not repo:
        return 1

    secrets = repo.scan()

    if len(secrets.data) > 0:
        _alert_on_secrets_found(repo, secrets.json(), args.output_hook)
    else:
        _update_tracked_repo(repo)

    return 0


def _alert_on_secrets_found(repo, secrets, output_hook):
    """
    :type repo: detect_secrets_server.repos.base_tracked_repo.BaseTrackedRepo

    :type secrets: dict
    :param secrets: output of
        detect_secrets.core.secrets_collection.SecretsCollection.json()

    :type output_hook: detect_secrets_server.hooks.base.BaseHook
    """
    CustomLog().getLogger().error('Secrets found in %s', repo.name)

    _set_authors_for_found_secrets(repo, secrets)

    output_hook.alert(repo.name, secrets)


def _update_tracked_repo(repo):
    """Save and update records, since the latest scan indicates that the
    most recent commit is clean.
    """
    CustomLog().getLogger().info('No secrets found for %s', repo.name)

    repo.update()
    repo.save(OverrideLevel.ALWAYS)


def _set_authors_for_found_secrets(repo, secrets):
    """Use git blame to try and identify the user who committed the
    potential secret. This allows us to follow up with a specific user if
    a secret is found.

    Modifies secrets in-place.
    """
    for filename in secrets:
        for potential_secret_dict in secrets[filename]:
            blame_info = repo.get_blame(
                filename,
                potential_secret_dict['line_number'],
            )

            potential_secret_dict['author'] = \
                _extract_user_from_git_blame_info(blame_info)


def _extract_user_from_git_blame_info(info):
    """As this tool is meant to be used in an enterprise setting, we assume
    that the email address of the committer uniquely identifies a given user.

    This function extracts that information.
    """
    info = info.split()

    index_of_mail = info.index('author-mail')
    email = info[index_of_mail + 1]     # Eg. `<khock@yelp.com>`
    index_of_at_symbol = email.index('@')

    # This will skip the prefix `<`, and extract the user up to the `@` sign.
    return email[1:index_of_at_symbol]