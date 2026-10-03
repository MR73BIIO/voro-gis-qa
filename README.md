# Baza Drzew 🌳 — Final Project CS50P

#### Video Demo: <TUTAJ WSTAW LINK DO NAGRANIA NA YOUTUBE>

#### Description:

Baza Drzew to konsolowy program w Pythonie do prowadzenia rejestru drzew
w terenie. Pozwala dodawać drzewa z podstawowymi danymi (gatunek,
lokalizacja, obwód pnia, wysokość, stan zdrowotny, uwagi), przeglądać je,
wyszukiwać po gatunku, filtrować po stanie zdrowotnym, liczyć statystyki
całej bazy i — co jest sercem tego projektu — automatycznie wskazywać,
które drzewa wymagają kontroli.

To pierwszy, namacalny krok w stronę cyfrowej inwentaryzacji zieleni
(„drzewa + dane"), nad którą pracuję poza samym kursem: łączę wiedzę
o drzewach z Pythonem, a w kolejnych krokach z GIS i danymi z drona.
Dane testowe w tym repo pochodzą z drzew na mojej własnej posesji —
to nie jest ćwiczenie w oderwaniu od rzeczywistości, to realny początek
mojej własnej bazy.

### Co potrafi program

- **Dodawanie drzewa** — gatunek, lokalizacja, obwód pnia (cm), wysokość (m),
  stan zdrowotny (dobry / dostateczny / zly), uwagi.
- **Przeglądanie wszystkich drzew** w bazie.
- **Wyszukiwanie po gatunku** — fragment nazwy, bez rozróżniania wielkości liter.
- **Filtrowanie po stanie zdrowotnym**.
- **Statystyki** — liczba drzew, podział wg gatunku i stanu, średni obwód pnia.
- **Drzewa do kontroli** — funkcja `needs_inspection`, która oznacza drzewa
  w złym stanie ORAZ duże drzewa (obwód > 200 cm), nawet jeśli ich stan
  jest oceniony jako dobry. To nie jest przypadek — w realnym zarządzaniu
  zieleni duże, stare drzewa wymagają regularnej kontroli (tzw. Regelkontrolle)
  niezależnie od chwilowej oceny, bo ich upadek niesie dużo większe ryzyko.
  Ta jedna funkcja jest mostem między ćwiczeniem programistycznym
  a tym, czym realnie chcę się zajmować.
- **Trwałość danych** — baza zapisuje się i wczytuje z pliku `drzewa.csv`,
  więc dane nie giną między uruchomieniami.

### Jak uruchomić

Program używa tylko biblioteki standardowej Pythona (`csv`, `sys`) —
nie trzeba niczego dodatkowo instalować.

```bash
python3 project.py
```

Żeby uruchomić testy:

```bash
pip install pytest
pytest test_project.py
```

### Struktura plików

- **`project.py`** — cały program. Zawiera `main()` oraz pięć
  niezależnie testowalnych funkcji: `add_tree`, `search_by_species`,
  `filter_by_condition`, `compute_stats`, `needs_inspection`. Plus
  funkcje wejścia/wyjścia (`load_trees`, `save_trees`, `wczytaj_liczbe`,
  `wczytaj_stan`, `pokaz_drzewa`, `pokaz_statystyki`), które obsługują
  konsolę i plik, ale nie są jednostkowo testowane — bo ich zadaniem
  jest komunikacja ze światem zewnętrznym (input/print/plik), nie logika.
- **`test_project.py`** — testy dla pięciu głównych funkcji logiki:
  poprawne dodawanie drzewa (i to, że nie modyfikuje oryginalnej listy),
  wyszukiwanie, filtrowanie, statystyki (w tym przypadek pustej bazy)
  oraz wskazywanie drzew do kontroli.

### Decyzje projektowe

Najważniejszy podział w tym kodzie to oddzielenie **logiki** od
**wejścia/wyjścia**. Funkcje takie jak `add_tree` czy `compute_stats`
nie pytają nikogo o nic i nie drukują niczego na ekran — dostają dane,
zwracają wynik, i tyle. Dzięki temu można je przetestować bez symulowania
klawiatury. Cała interakcja z użytkownikiem (pytania, menu, zapis do
pliku) żyje w osobnych funkcjach, wywoływanych z `main()`.

`add_tree` zwraca **nową** listę (`drzewa + [nowe_drzewo]`) zamiast
modyfikować przekazaną listę w miejscu — to świadoma decyzja, żeby
funkcja była czysta i przewidywalna przy testowaniu.

### Pomysły na rozwój

- [ ] Edycja i usuwanie istniejącego drzewa
- [ ] Współrzędne GPS i eksport do formatu czytelnego dla GIS (np. GeoJSON)
- [ ] Import danych z inwentaryzacji terenowej / z drona
- [ ] Prosty interfejs graficzny zamiast konsoli
- [ ] Eksport raportu z drzewami do kontroli do pliku PDF
