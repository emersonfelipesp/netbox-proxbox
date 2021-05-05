## Getting Help

If you encounter any issues installing or using Proxbox, try one of the
following resources to get assistance. Please **do not** open a GitHub issue
except to report bugs or request features.

### GitHub Discussions

GitHub's discussions are the best place to get help or propose rough ideas for
new functionality. Their integration with GitHub allows for easily cross-
referencing and converting posts to issues as needed. There are several
categories for discussions:

* **General** - General community discussion
* **Ideas** - Ideas for new functionality that isn't yet ready for a formal
  feature request
* **Q&A** - Request help with installing or using NetBox

### Slack

For real-time chat, you can join the **#netbox** Slack channel on [NetDev Community](https://slack.netbox.dev/).
Unfortunately, the Slack channel does not provide long-term retention of chat
history, so try to avoid it for any discussions would benefit from being
preserved for future reference.

### Telegram

If you prefer, you can also join the **[telegram group](https://t.me/joinchat/jxhqhQCxEmNhZDJh)** to freely discuss about the project and get assistance from community.

## Reporting Bugs

* First, ensure that you're running the [latest stable version](https://github.com/N-Multifibra/netbox-proxbox)
of Proxbox and Netbox. If you're running an older version, it's possible that the bug has
already been fixed.
* Check following links to know the latest stable version for both applications:
  - [Netbox releases](https://github.com/netbox-community/netbox/releases)
  - [Proxbox releases](https://github.com/N-Multifibra/netbox-proxbox/releases)
 
* Next, check the GitHub [issues list](https://github.com/N-Multifibra/netbox-proxbox/issues)
to see if the bug you've found has already been reported. If you think you may
be experiencing a reported issue that hasn't already been resolved, please
click "add a reaction" in the top right corner of the issue and add a thumbs
up (+1). You might also want to add a comment describing how it's affecting your
installation. This will allow us to prioritize bugs based on how many users are
affected.

* When submitting an issue, please be as descriptive as possible. Be sure to
provide all information request in the issue template, including:

    * The environment in which NetBox is running
    * The exact steps that can be taken to reproduce the issue
    * Expected and observed behavior
    * Any error messages generated
    * Screenshots (if applicable)

* Please avoid prepending any sort of tag (e.g. "[Bug]") to the issue title and also keep in mind that we prioritize bugs based on their severity and how much work is required to resolve them.


## Feature Requests

* First, check the GitHub [issues list](https://github.com/netbox-community/netbox/issues)
to see if the feature you're requesting is already listed. (Be sure to search
closed issues as well, since some feature requests have been rejected.) If the
feature you'd like to see has already been requested and is open, click "add a
reaction" in the top right corner of the issue and add a thumbs up (+1). This
ensures that the issue has a better chance of receiving attention. Also feel
free to add a comment with any additional justification for the feature.
(However, note that comments with no substance other than a "+1" will be
deleted. Please use GitHub's reactions feature to indicate your support.)

* Before filing a new feature request, consider raising your idea on the community channels available, like Slack and Telegram (we don't have a mailing list yet). Feedback you receive there will help validate and shape the
proposed feature before filing a formal issue.

* Good feature requests are very narrowly defined. Be sure to thoroughly
describe the functionality and data model(s) being proposed. The more effort
you put into writing a feature request, the better its chance is of being
implemented. Overly broad feature requests will be closed.

* When submitting a feature request on GitHub, be sure to include all
information requested by the issue template, including:

    * A detailed description of the proposed functionality
    * A use case for the feature; who would use it and what value it would add
      to Proxbox
    * A rough description of changes necessary to the database schema (if
      applicable)
    * Any third-party libraries or other resources which would be involved

* Please avoid prepending any sort of tag (e.g. "[Feature]") to the issue
title. The issue will be reviewed by a moderator after submission and the
appropriate labels will be applied for categorization.

## Submitting Pull Requests

* If you're interested in contributing to Proxbox, I would suggest you to do it using [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) to set up your development environment. You can also use your own way, but be sure to develop it using [Netbox's code](https://github.com/netbox-community/netbox) and not a forked one, as it may change the normal behavior of Netbox.

### Before starting your code, discuss it with the community and project's maintainers

* Be sure to open an issue **before** starting work on a pull request, and
discuss your idea with the Proxbox maintainers before beginning work. This will
help prevent wasting time on something that might we might not be able to
implement. When suggesting a new feature, also make sure it won't conflict with
any work that's already in progress.

* Once you've opened or identified an issue you'd like to work on, ask that it
be assigned to you so that others are aware it's being worked on. A maintainer
will then mark the issue as "accepted."

* Any pull request which does _not_ relate to an **accepted** issue will be closed.

* All new functionality must include relevant tests where applicable.

### Use develop branch to contribute

* When submitting a pull request, please be sure to work off of the `develop`
branch, rather than `main`. The `develop` branch is used for ongoing
development, while `main` is used for tagging stable releases.

* In most cases, it is not necessary to add a changelog entry: A maintainer will
take care of this when the PR is merged. (This helps avoid merge conflicts
resulting from multiple PRs being submitted simultaneously.)

## Commenting

Only comment on an issue if you are sharing a relevant idea or constructive
feedback. **Do not** comment on an issue just to show your support (give the
top post a :+1: instead) or ask for an ETA. These comments will be deleted to
reduce noise in the discussion.
