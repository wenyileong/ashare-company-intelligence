# Compliance note

This note explains the legal and ethical choices built into A-share Company Intelligence and what remains the responsibility of the researcher who uses it. It is a guide to the design, not legal advice; the position in a particular project depends on where the researcher is, what is collected and how the results are shared, and should be checked against the current texts and, where necessary, with the institution's data-protection officer or counsel.

## 1. Collection

The program collects only material that the sources publish openly: the statutory disclosure platform CNINFO, the exchanges' public pages and a free public price feed. It is designed so that collection stays within what those sources permit:

- one request per second by default, with retries backed off, and an identifying user agent that should be completed with the researcher's contact details (`ASHARE_USER_AGENT`);
- no login, no circumvention of CAPTCHAs, authentication, access controls or rate limits, and no use of undocumented private interfaces beyond the public query endpoints used by the sources' own web pages;
- the daily update queries the market as a whole (one query per exchange and day) rather than every company separately, which keeps the request volume to roughly a thousand requests a day.

These choices reflect, among other things, the Cybersecurity Law of the People's Republic of China 2016, art 27 (no unlawful intrusion into, or interference with the normal functioning of, other people's networks), and the Regulations on Network Data Security Management 2024 (effective 1 January 2025), art 18, under which a person using automated tools to access or collect network data must assess the effect on the network service and must not unlawfully intrude into networks or interfere with their normal operation. Unauthorised access to computer information systems may also engage the Criminal Law of the People's Republic of China, arts 285 and 286. Researchers should read each source's terms of use, which may restrict automated access or reuse, and should respect them.

## 2. Licences

Every row in the database is assigned a licence class from its source (see the [methods document](methods.md), section 8). Vendor data imported under a licence (for example ESG ratings, Shenwan industry classifications or index constituent files) are classed as LICENSED and are **excluded from every release unless the researcher chooses otherwise**, and the manifest records what was left out. Because the program cannot know where an imported file came from, every import is treated as licensed until the researcher tags its source with another class.

The public price feed is classed separately (PUBLIC_FEED). It is not exchange-authoritative, and its provider's terms govern redistribution; researchers who intend to publish price data should consider excluding this class (`--exclude PUBLIC_FEED`) or substituting licensed data they are entitled to share.

Statutory disclosures are public, but that does not by itself settle every question of reuse. Facts and figures are generally free to use; extended verbatim text of documents is a different matter, which is one reason why pseudonymised releases omit the document text.

## 3. Personal information

The data include personal information: the names, gender, age, remuneration, shareholdings and career histories of directors, supervisors and senior officers, and the names of natural-person shareholders, pledgors and controllers. Listed companies must disclose this information, but its further processing remains subject to data-protection law.

### People's Republic of China

Under the Personal Information Protection Law of the People's Republic of China 2021 (PIPL), personal information includes any information relating to an identified or identifiable natural person (art 4). Processing personal information that the individual has disclosed, or that has otherwise been lawfully disclosed, is permitted within a reasonable scope (arts 13(1)(vi) and 27), unless the individual has expressly refused; consent is required where processing such information has a significant effect on the individual's rights and interests (art 27). The PIPL may also apply to processing outside China that analyses or assesses the conduct of individuals in China (art 3(2)(ii)), and transfers of personal information out of China are regulated (arts 38 to 40).

The PIPL distinguishes de-identification (去标识化), processing after which the information cannot identify a specific person without additional information, from anonymisation (匿名化), after which the information cannot identify anyone and cannot be restored (art 73(iii) and (iv)). Only anonymised information falls outside the law. **The pseudonymisation offered by the program is de-identification, not anonymisation**: a director's identifier, combined with the company, role and dates, can often be linked back to the person from the company's own annual report.

### United Kingdom and European Union

For researchers subject to the UK GDPR or the EU GDPR, pseudonymised data likewise remain personal data (UK GDPR, art 4(5) and recital 26). Processing for research typically relies on legitimate interests or a public task (art 6(1)(e) or (f)), with the safeguards of art 89, of which pseudonymisation is named as one (art 89(1)); the information duty for data not obtained from the data subject may be relaxed for research where providing it would involve disproportionate effort (art 14(5)(b)). In the United Kingdom see also the Data Protection Act 2018, sch 2 pt 6 para 27, and the amendments made by the Data (Use and Access) Act 2025, which are being brought into force in stages; the current text should be checked.

### What the program does

- **Minimisation by default.** Releases never include local file paths, raw provider responses, operational tables or the review queue.
- **Pseudonymisation (optional).** Names of natural persons are replaced with keyed identifiers (HMAC-SHA256 under a secret key kept outside the release). Raw text columns and document text are dropped; known names are replaced in titles and other free text. Ages and birth years can be grouped into five-year bands, and free text can be dropped entirely.
- **Stable identifiers.** The same key gives the same identifiers in later releases, so the key should be kept, and kept private: anyone who holds it can test whether a given name is in the data.
- **Organisations are not pseudonymised**, because they are not natural persons and are needed to interpret the data.

### What remains with the researcher

- deciding whether the project needs personal information at all, and at what level of detail (for example, board-level aggregates may suffice);
- a lawful basis, an ethics approval where the institution requires one, and a record of processing;
- secure storage of the database and the pseudonymisation key;
- assessing re-identification risk before sharing a release, and choosing the stronger options (banding, dropping free text) or sharing under a data-use agreement where the risk is material;
- checking cross-border transfer rules before moving personal information between jurisdictions.

## 4. Reproducibility and transparency

Every release records the software version, schema revision, a database fingerprint and the hash of every file, together with the licence classes excluded and the pseudonymisation settings, so that a published dataset can be described accurately and its provenance verified.
