A-share Company Intelligence v2.0.7
=================================

Install
  Run AShareScraper-2.0.7-setup.exe (no administrator rights needed), or
  unzip the portable zip (and its command-line add-on) into one folder.
  Both routes give the desktop application
  (AShareScraper.exe) and the command line (ashare-cli.exe).
  If Windows shows "Windows protected your PC", choose More info > Run anyway
  (this build is not code-signed).

First run (the Getting started page lists these steps)
  1. Self-test      > Run the live self-test (all checks should PASS)
  2. Universe       > Update the company list
  3. Disclosures    > Catalogue announcements (try one code, e.g. 600519, with
                      "Download documents" ticked)
  4. Financials     > Extract figures from reports
  5. Validate       > Run all checks
  6. Company        > Company report (opens in your browser)
  For the whole market, use Operations > Daily update.

Where your data are kept
  Documents\AShareScraper (change it under Settings). It holds the database
  (ashares.db), original documents, exports, reports, panels, releases and
  run_log.txt, which records every action with its equivalent command.
  Upgrading the program upgrades the database and first saves a backup copy
  (ashares.db.bak-...). Installing or uninstalling never touches this folder.

Documentation (docs folder, also on the Start menu)
  user_guide.html       how to use the program
  methods.html          how the data are produced (for citation)
  codebook.html         every panel variable
  compliance.html       licences, personal information, pseudonymisation
  developer_guide.html  extending and building the program

Command line
    ashare-cli --help
    ashare-cli report 600519
    ashare-cli release --pseudonymise

Keep the whole folder together: the programs need the _internal folder.

Licence
  A-share Company Intelligence is licensed under the PolyForm Strict License 1.0.0 (LICENSE.md):
  noncommercial use only; no distribution and no changes. Copyright Leong, Wen Yi.

Third-party components
  The program bundles third-party components (the Python runtime and libraries such as
  pypdf, PDFium, SQLAlchemy and httpx). Each keeps its own licence; THIRD_PARTY_NOTICES.txt
  lists them with their versions and reproduces their licence and copyright notices.
