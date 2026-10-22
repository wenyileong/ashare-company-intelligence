# Security policy

## Supported versions

Only the latest release receives fixes. Earlier versions are not updated; please upgrade before reporting a problem.

## Reporting a vulnerability

Please report a security problem privately, through GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue.

Please include the version, the steps to reproduce the problem and what an attacker could achieve. You will receive an acknowledgement, and the report will be kept confidential until a fix is released. This is a research project maintained by one person, so no response time can be guaranteed.

## Scope

In scope:
- the Windows installer and the portable downloads published on the releases page;
- the handling of documents and responses from the sources (for example a crafted PDF or a malformed response that leads to code execution or to files written outside the program's folders);
- the update check, when it is configured;
- the local database and the files the program writes.

Out of scope:
- vulnerabilities in the sources' own websites;
- problems that need an attacker who already controls the computer or the user's account;
- the absence of a code signature on the downloads, which is known (check each download against `SHA256SUMS.txt` on the release page).
