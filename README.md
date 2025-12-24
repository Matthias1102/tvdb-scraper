# Tools for fetching Eisenbahn-Romantik eposode titles from The TVDB

## Initial Fetching

Fetch all regular episodes from the TVDB:
```
./fetch-railway-romance-episodes.py
```
Fetch all specials from the TVDB:
```
./fetch-railway-romance-specials.py
```
Merge JSON lists with episodes and specials into one JSON list:
```
./merge_json_lists.py eisenbahn_romantik_tvdb_episodes.json eisenbahn_romantik_tvdb_specials.json eisenbahn_romantik_tvdb_episodes_and_specials.json
```
Merge the CSV files as well:
```
cat  eisenbahn_romantik_tvdb_episodes.csv > eisenbahn_romantik_tvdb_episodes_and_specials.csv
cat  eisenbahn_romantik_tvdb_specials.csv >> eisenbahn_romantik_tvdb_episodes_and_specials.csv
```
Parse the film list from MediathekView and align all episode/special names with the names from the TVDB:
```
./parse_tvdb_film_list.py
```
Now it's time to review the table `MediathekView-Filmliste-Eisenbahn-Romantik_with_TVDB_matches.xlsx`.
Have all names from the MediathekView list been mapped to the correct TVDB episode names? If not,
edit the entries in the "new_filenames" column. After the review, save the table to
`MediathekView-Filmliste-Eisenbahn-Romantik_with_TVDB_matches_reviewed.xlsx`.

Iterate over the reviewed table and check which episodes already exist. Write the output to
`MediathekView-Filmliste-Eisenbahn-Romantik_final.xlsx`:
```
./mark_existing_files.py \
    MediathekView-Filmliste-Eisenbahn-Romantik_with_TVDB_matches_reviewed.xlsx \
    /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik/ \
    MediathekView-Filmliste-Eisenbahn-Romantik_final.xlsx
```
Now copy & rename all files according to the mappings in
`MediathekView-Filmliste-Eisenbahn-Romantik_final.xlsx`:
```
./copy_from_xlsx_map.py MediathekView-Filmliste-Eisenbahn-Romantik_final.xlsx \
    ~/Videos/ ~/Videos2/  \
    --dry-run
```
Find duplicate episodes, considering the videos that we already have from the recent years:
```
./find_er_duplicates.py /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik-neu
```
Identify which ER episodes we have in the filesystem, the result is written to
`eisenbahn_romantik_tvdb_episodes_and_specials_with_filesystem_check`:
```
./check_er_csv_against_filesystem.py eisenbahn_romantik_tvdb_episodes_and_specials.csv  /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik/
```

## Daily use: Download latest MediathekView Filmliste and Identify not-yet-downloaded episodes

Download the MediathekView Filmliste and save it as `MediathekView-Eisenbahn-Romantik.json`:
```
./download_er_filmliste.py
```

Convert the JSON file into a CSV file with columns: title, date, start_time, duration, episode.
ONLY episodes WITH an episode number ("Folge <n>") are kept. Any duplicates are removed:
```
./convert_er_filmliste_json_to_csv.py MediathekView-Eisenbahn-Romantik.json  MediathekView-Eisenbahn-Romantik.csv
```
Identify missing episode videos and report them to `MediathekView-Eisenbahn-Romantik_missing.csv`:
```
./report_missing_er_files.py MediathekView-Eisenbahn-Romantik.csv  /mnt/omv-data1/Video/Dokumentationen/Eisenbahn-Romantik/ eisenbahn_romantik_tvdb_episodes_and_specials.json
```
