# Privacy policy: Skrutable Sanskrit Tools browser extension

Effective 27 November 2026.

The Skrutable Sanskrit Tools extension (for Chrome and Firefox) collects no personal information, has no accounts, and contains no analytics or tracking.

## What leaves your browser

- **Text you split into words.** When you click **Split Words**, the text in the panel's input box is sent over HTTPS to the word-splitting server you have chosen in the settings, together with the splitting options. The two servers are:
  - Dharmamitra, at `dharmamitra.org` (the default)
  - the 2018 EMNLP splitter, at `2018emnlp-sanskrit-splitter-server.duckdns.org`

  The splitter returns the split text to the panel. Nothing is sent unless you click Split Words, and nothing else is sent with the text. Those services' own policies cover what they do with requests they receive.
- **Meter melodies.** When you play a melody after scansion or meter identification, the audio file is loaded from `www.skrutable.info`. No text is sent.

Transliteration, scansion and meter identification run entirely inside your browser.

## What stays in your browser

- Your settings (schemes, display options, splitter choice, font size) are kept in the browser's extension storage. If you use your browser's sync, the browser syncs them across your devices.
- The panel's last input and output text and its light or dark theme are kept in the browser's local storage for the extension, so they are there when you reopen the panel. Clearing the panel or removing the extension deletes them.

The extension sends none of this anywhere.

## Permissions

The extension reads the text you have selected only when you click its toolbar icon or choose **Process with Skrutable** from the right-click menu. It doesn't read pages in the background.

## Contact

Questions or concerns: open an issue at [github.com/tylergneill/skrutable_front_end](https://github.com/tylergneill/skrutable_front_end/issues).

## Changes

Any change to this policy will be made in this file, with a new effective date.
