# ml_project

Utilities and data for scraping and analyzing movie screenplays from [IMSDb](https://imsdb.com) to explore conversational structure at scale.

---

## Repository contents

- **`imsdb_to_csv.py`** — Python script that crawls IMSDb and compiles scripts into a single CSV.  
- **`imsdb_scripts.csv`** — Dataset produced by the scraper; each row corresponds to one script page and includes the raw text and metadata.
- (Optional) **`.gitattributes`** — Configures [Git LFS](https://git-lfs.github.com/) to store large artifacts (recommended for `imsdb_scripts.csv`).  
- (Optional) **`.gitignore`** — Ignores Jupyter checkpoints, caches, etc.

> Tip: If you are using GitHub, enable **Git LFS** and track large files, e.g.
>
> ```bash
> git lfs install
> git lfs track "imsdb_scripts.csv"
> git add .gitattributes && git commit -m "Enable LFS for dataset"
> ```

---

## Dataset: `imsdb_scripts.csv`

**Row count:** 1,252  
**Unique movies (by `title`):** 1,221 (31 duplicate-title rows)

### Data dictionary (columns)

- **`title`** – Movie title as listed on IMSDb (may contain duplicates or slight variations).  
- **`source_url`** – IMSDb page URL where the script was obtained.  
- **`writers`** – Credited screenwriter names from IMSDb; multiple writers are separated by `|`.  
- **`genres`** – One or more IMSDb genres; values are `|`-separated (e.g., `Crime|Drama|Thriller`).  
- **`draft_info`** – Draft/version note found on the page (e.g., “Shooting Draft,” dates). Often blank.  
- **`script_text`** – Raw text of the screenplay: scene headings, action lines, dialogue, etc.

### Conversation metrics (approximate)

Computed with a heuristic parser that treats **ALL‑CAPS** lines as speaker tags (e.g., `JOHN`, `SARAH (V.O.)`), ignores common scene headings (`INT.`, `EXT.`, `FADE IN:`, etc.), collapses repeated turns by the same speaker, and then counts:

- **Total conversational turns:** **1,247,179**  
- **Total conversational exchanges:** **1,245,935**  
  - *Definition:* number of times the speaker changes across all scripts.
- **Unique character interactions (pairs):** **320,278**  
  - *Definition:* unique unordered pairs of characters who speak in adjacent turns at least once.

> These are estimates; screenplay formatting varies across IMSDb pages.

---
## Dataset: `Cornell Movie-Dialog Corpus`

Distributed together with:

"Chameleons in imagined conversations: A new approach to understanding coordination of linguistic style in dialogs"
Cristian Danescu-Niculescu-Mizil and Lillian Lee
Proceedings of the Workshop on Cognitive Modeling and Computational Linguistics, ACL 2011.

(this paper is included in this zip file)

NOTE: If you have results to report on these corpora, please send email to cristian@cs.cornell.edu or llee@cs.cornell.edu so we can add you to our list of people using this data.  Thanks!


Contents:

	A) Brief description
	B) Files description
	C) Details on the collection procedure
	D) Contact


A) Brief description:

This corpus contains a metadata-rich collection of fictional conversations extracted from raw movie scripts:

- 220,579 conversational exchanges between 10,292 pairs of movie characters
- involves 9,035 characters from 617 movies
- in total 304,713 utterances
- movie metadata included:
	- genres
	- release year
	- IMDB rating
	- number of IMDB votes
	- IMDB rating
- character metadata included:
	- gender (for 3,774 characters)
	- position on movie credits (3,321 characters)


B) Files description:

In all files the field separator is " +++$+++ "

- movie_titles_metadata.txt
	- contains information about each movie title
	- fields: 
		- movieID, 
		- movie title,
		- movie year, 
	   	- IMDB rating,
		- no. IMDB votes,
 		- genres in the format ['genre1','genre2', ,'genreN']

- movie_characters_metadata.txt
	- contains information about each movie character
	- fields:
		- characterID
		- character name
		- movieID
		- movie title
		- gender ("?" for unlabeled cases)
		- position in credits ("?" for unlabeled cases) 

- movie_lines.txt
	- contains the actual text of each utterance
	- fields:
		- lineID
		- characterID (who uttered this phrase)
		- movieID
		- character name
		- text of the utterance

- movie_conversations.txt
	- the structure of the conversations
	- fields
		- characterID of the first character involved in the conversation
		- characterID of the second character involved in the conversation
		- movieID of the movie in which the conversation occurred
		- list of the utterances that make the conversation, in chronological 
			order: ['lineID1','lineID2', ,'lineIDN']
			has to be matched with movie_lines.txt to reconstruct the actual content

- raw_script_urls.txt
	- the urls from which the raw sources were retrieved

C) Details on the collection procedure:

We started from raw publicly available movie scripts (sources acknowledged in 
raw_script_urls.txt).  In order to collect the metadata necessary for this study 
and to distinguish between two script versions of the same movie, we automatically
 matched each script with an entry in movie database provided by IMDB (The Internet
 Movie Database; data interfaces available at http://www.imdb.com/interfaces). Some
 amount of manual correction was also involved. When  more than one movie with the same
 title was found in IMBD, the match was made with the most popular title 
(the one that received most IMDB votes)  

After discarding all movies that could not be matched or that had less than 5 IMDB 
votes, we were left with 617 unique titles with metadata including genre, release 
year, IMDB rating and no. of IMDB votes and cast distribution.  We then identified 
the pairs of characters that interact and separated their conversations automatically 
using simple data processing heuristics. After discarding all pairs that exchanged 
less than 5 conversational exchanges there were 10,292 left, exchanging 220,579 
conversational exchanges (304,713 utterances).  After automatically matching the names 
of the 9,035 involved characters to the list of cast distribution, we used the 
gender of each interpreting actor to infer the fictional gender of a subset of 
3,321 movie characters (we raised the number of gendered 3,774 characters through
 manual annotation). Similarly, we collected the end credit position of a subset 
of 3,321 characters as a proxy for their status.


D) Contact:

Please email any questions to: cristian@cs.cornell.edu (Cristian Danescu-Niculescu-Mizil)
---
## How to reproduce the CSV with `imsdb_to_csv.py`

### Requirements

Python 3.9+ and typical data/scraping libraries. For example:

```bash
pip install pandas requests beautifulsoup4 tqdm lxml
```

### Basic usage

```bash
# Run with defaults (see the script header for adjustable options)
python imsdb_to_csv.py
```

If the script supports arguments (letters to crawl, max items, output path), typical patterns look like:

```bash
python imsdb_to_csv.py --letters A-Z --max-items 0 --out imsdb_scripts.csv
```

(If not, configure those values near the top of the script.)

### Notes on respectful crawling

- Honor IMSDb’s robots.txt and terms of use.
- Add polite delays between requests.
- Cache pages where possible to avoid repeat traffic.
