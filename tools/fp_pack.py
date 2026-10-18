#!/usr/bin/env python3
"""Fill in the false-positive reports for every antivirus vendor: one text file per vendor, ready to paste.

    python tools/fp_pack.py --zip dist/T5DR-Online-1.0.2.zip --exe "dist/T5DR-Online-1.0.2/T5DR Online.exe" ^
        --release-url https://github.com/TheWishin/T5DROnline/releases/tag/v1.0.2 --vt-url <VirusTotal link> ^
        --out build/fp-pack [--detection Webroot=Win.Trojan.Gen --detection Trapmine=Suspicious.low.ml.score ...]
        [--only Webroot Trapmine]

Reads the two files (size, SHA-256) and writes OUT/<vendor>.txt with: where to send it (form link or
e-mail address), the subject, what to attach and the body, with the file facts and the vendor's own
detection name filled in. Uploads and sends nothing: you do that. The vendor list is the one in
docs/RELEASING.md "Reporting false positives" (contacts from VirusTotal's own false-positive list).
"""
import argparse
import hashlib
import os
import sys

# name -> (kind, where, how to use it, same engine as Bitdefender?)
VENDORS = {
    "Webroot": ("form", ["https://www.webroot.com/us/en/business/support/vendor-dispute-contact-us",
                         "https://snup.webrootcloudav.com/SkyStoreFileUploader/upload.aspx"],
                "Vendor dispute form with your e-mail address; or upload the exe at the second link and choose the "
                "reason \"False Positive detection\".", False),
    "Trapmine": ("mail", ["fp@trapmine.com"], "E-mail; attach the exe.", False),
    "Symantec": ("form", ["https://symsubmit.symantec.com"],
                 "Click \"Clean software incorrectly detected\", upload the exe (or give the link), add your e-mail "
                 "(the tracking number goes there).", False),
    "Bkav": ("mail", ["fpreport@bkav.com", "bkav@bkav.com"], "E-mail to the first address, copy the second; attach the exe.",
             False),
    "SecureAge": ("form", ["https://www.secureage.com/support/report-false-positive",
                           "https://www.secureage.com/contact-us"],
                  "Put the exe in a ZIP first, upload it at the first link. Help: docs@secureage.com.", False),
    "Bitdefender": ("mail", ["virus_submission@bitdefender.com",
                             "https://www.bitdefender.com/consumer/support/answer/29358/",
                             "https://www.bitdefender.com/business/support/en/77211-343057-submitting-sample-files-and-websites-for-analysis.html"],
                    "E-mail with the exe (in a ZIP if the mail server refuses it), or the web form: choose "
                    "\"False positive\".", False),
    "ALYac": ("mail", ["esrc@estsecurity.com"], "E-mail; attach the exe. (Uses Bitdefender's engine too.)", True),
    "Arcabit": ("mail", ["vt.fp@arcabit.pl"], "E-mail; attach the exe. (Uses Bitdefender's engine too.)", True),
    "Emsisoft": ("mail", ["submit@emsisoft.com", "fp@emsisoft.com", "https://www.emsisoft.com/en/support/contact/"],
                 "E-mail one of the first two addresses, or use the contact form. (Uses Bitdefender's engine too.)", True),
    "GData": ("form", ["https://www.gdata.de/help/en/general/GeneralInformation/submitFileAppURL/"],
              "The form on that page. (Uses Bitdefender's engine too.)", True),
    "VIPRE": ("form", ["https://helpdesk.vipre.com/hc/en-us/requests/new"],
              "New request, subject and body below. (Uses Bitdefender's engine too.)", True),
    "Microsoft": ("form", ["https://www.microsoft.com/wdsi/filesubmission"],
                  "Windows Defender's own submission page: choose \"Software developer\", upload the exe, say "
                  "\"I believe this file is clean\".", False),
}

BODY = """Hello,

this is a false positive report for an open source program.

Program:     {name}  ({size:,} bytes)
SHA-256:     {exe_sha}
Archive:     {zip_name}  ({zip_size})
SHA-256:     {zip_sha}
Detection:   {detection}
VirusTotal:  {vt}
Release:     {release}
Source:      https://github.com/TheWishin/T5DROnline-Source  (MIT license)

What it is: T5DR Online is an open source Windows port of a PlayStation 3 fighting game, with online play.
"T5DR Online.exe" is a small starter (about 120 KB, built with Microsoft Visual C++ from
launcher/stub/t5dr_stub.c). It has one job: start python\\pythonw.exe with launcher\\t5dr_launcher.pyw from its
own folder. The starter itself makes no network connection, writes no file and changes no setting. The zip
holds the launcher (Python and tkinter, with a private copy of CPython {python}), the game runtime
runtime\\t5dr.exe, an LLVM compiler, and no game files. Online play connects to a lobby server the player
chooses; the launcher can ask GitHub for newer releases of the project.

Please check the file and remove the detection. Thank you.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--zip", required=True)
    ap.add_argument("--exe", required=True, help="the T5DR Online.exe of that release")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release-url", default="<release link>")
    ap.add_argument("--vt-url", default="<VirusTotal link>")
    ap.add_argument("--python", default="3.12")
    ap.add_argument("--detection", action="append", default=[], metavar="VENDOR=NAME",
                    help="the vendor's detection name, as VirusTotal shows it (repeatable)")
    ap.add_argument("--only", nargs="+", help="only these vendors")
    a = ap.parse_args()
    det = dict(d.split("=", 1) for d in a.detection if "=" in d)
    os.makedirs(a.out, exist_ok=True)
    exe_sha, zip_sha = sha256(a.exe), sha256(a.zip)
    zip_name = os.path.basename(a.zip)
    zip_size = f"{os.path.getsize(a.zip) / 1e6:.1f} MB"
    written = []
    for vendor, (kind, where, how, bd) in VENDORS.items():
        if a.only and vendor not in a.only:
            continue
        name = os.path.basename(a.exe)
        detection = det.get(vendor, "<detection name shown by " + vendor + ">")
        body = BODY.format(name=name, size=os.path.getsize(a.exe), exe_sha=exe_sha, zip_name=zip_name, zip_size=zip_size,
                           zip_sha=zip_sha, detection=detection, vt=a.vt_url, release=a.release_url, python=a.python)
        text = (f"Vendor:   {vendor}\n"
                f"Send via: {'e-mail' if kind == 'mail' else 'web form / portal'}\n"
                + "".join(f"{'To/Link:' if i == 0 else '        '}  {w}\n" for i, w in enumerate(where))
                + f"How:      {how}\n"
                + f"Subject:  False positive: {name} ({detection})\n"
                + f"Attach:   {name}  (the 124 KB exe; the zip is too big for most forms, use the link)\n"
                + ("Note:     same engine as Bitdefender; when Bitdefender removes its detection this one usually "
                   "follows. Report after a week if it still flags.\n" if bd else "")
                + "\n----- body -----\n" + body)
        path = os.path.join(a.out, vendor + ".txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        written.append(path)
    print(f"{len(written)} report(s) in {a.out}: " + ", ".join(os.path.splitext(os.path.basename(p))[0] for p in written))


if __name__ == "__main__":
    sys.exit(main())
