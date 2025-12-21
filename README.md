
Fetch all regular episodes from the TVDB
```
./fetch-railway-romance-episodes.py
```
Fetch all specials from the TVDB
```
./fetch-railway-romance-specials.py
```
Merge JSON lists with episodes and specials into one JSON list
```
merge_json_lists.py eisenbahn_romantik_tvdb_episodes.json eisenbahn_romantik_tvdb_specials.json eisenbahn_romantik_tvdb_episodes_and_specials.json
```
Merge the csv files as well
```
cat  eisenbahn_romantik_tvdb_episodes.csv > eisenbahn_romantik_tvdb_episodes_and_specials.csv
cat  eisenbahn_romantik_tvdb_specials.csv >> eisenbahn_romantik_tvdb_episodes_and_specials.csv
```
Parse the film list from MediathekView and align all episode/special names with the names from the TVDB.
```
parse_tvdb_film_list.py
```

