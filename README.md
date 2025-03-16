# Celcat Calendar Scraper 📆

An asynchronous Python library for scraping Celcat calendar systems.

## Installation 🚀

```sh
pip install celcat-scraper
```

## Features 🌟

* Event data filtering 🧹
* Async/await support for better performance 🔀
* Rate limiting with adaptive backoff ⏳
* Optional caching support 💾
* Optional reusable aiohttp session ♻️
* Automatic session management 🍪
* Batch processing of events 📦
* Error handling and retries 🚨

## Usage ⚙️

Basic example of retrieving calendar events:

```python
import asyncio
from datetime import date, timedelta
from celcat_scraper import CelcatConfig, CelcatScraperAsync

async def main():
    # Configure the scraper
    config = CelcatConfig(
        url="https://university.com/calendar",
        username="your_username",
        password="your_password",
        include_holidays=True,
    )

    # Create scraper instance and get events
    async with CelcatScraperAsync(config) as scraper:
        start_date = date.today()
        end_date = start_date + timedelta(days=30)

        # Recommended to store events locally and reduce the amout of requests
        file_path = "store.json"
        events = scraper.deserialize_events(file_path)

        events = await scraper.get_calendar_events(
            start_date, end_date, previous_events=events
        )

        for event in events:
            print(f"Event {event['id']}")
            print(f"Course: {event['category']} - {event['course']}")
            print(f"Time: {event['start']} to {event['end']}")
            print(f"Location: {', '.join(event['rooms'])} at {', '.join(event['sites'])} - {event['department']}")
            print(f"Professors: {', '.join(event['professors'])}")
            print("---")

        # Save events for a future refresh
        scraper.serialize_events(events, file_path)

if __name__ == "__main__":
    asyncio.run(main())
```

## Filtering 🧹

Celcat Calendar data is often messy, and needs to be processed before it can be used.
For example, the same course may have several different names in different events.
Filtering allows these attributes to be standardized.

### Usage ⚙️

> ℹ️ **Info**: Each filter argument is optional. When course_strip_redundant is enabled, using remembered_strips is recommended.

> ⚠️ **Warning**: Disabling filters will require you to reset your previous events and refetch to undo changes.

```python
import asyncio
from datetime import date, timedelta
import json
from celcat_scraper import CelcatFilterConfig, FilterType, CelcatConfig, CelcatScraperAsync

async def main():
    # Load remembered_strips from a file
    remembered_strips = []
    try:
        with open("remembered_strips.json", "r") as f:
            remembered_strips = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        remembered_strips = []

    # Create a list of manual course replacements
    course_replacements = {"English - S2": "English", "Mathematics": "Maths"}

    # Configure a filter
    filter_config = CelcatFilterConfig(
        filters = {
            FilterType.COURSE_TITLE,
            FilterType.COURSE_STRIP_MODULES,
            FilterType.COURSE_STRIP_CATEGORY,
            FilterType.COURSE_STRIP_PUNCTUATION,
            FilterType.COURSE_GROUP_SIMILAR,
            FilterType.COURSE_STRIP_REDUNDANT,
            FilterType.PROFESSORS_TITLE,
            FilterType.ROOMS_TITLE,
            FilterType.ROOMS_STRIP_AFTER_NUMBER,
            FilterType.SITES_TITLE,
            FilterType.SITES_REMOVE_DUPLICATES,
        }
        course_remembered_strips=remembered_strips,
        course_replacements=course_replacements,
    )

    config = CelcatConfig(
        url="https://university.com/calendar",
        username="your_username",
        password="your_password",
        include_holidays=True,
        # Pass the filter as an argument
        filter_config=filter_config,
    )

    async with CelcatScraperAsync(config) as scraper:
        start_date = date.today()
        end_date = start_date + timedelta(days=30)

        events = scraper.deserialize_events("store.json")
        events = await scraper.get_calendar_events(
            start_date, end_date, previous_events=events
        )

        scraper.serialize_events(events, file_path)

    # Save the updated remembered_strips back to file
    with open("remembered_strips.json", "w") as f:
        json.dump(scraper.filter_config.course_remembered_strips, f)

if __name__ == "__main__":
    asyncio.run(main())
```

### Available Filters 🧹

| Filter | Description | Example |
| :---: | :--- | :--- |
| *_TITLE | Capitalize only the first letter of each word | MATHS CLASS -> Maths Class |
| COURSE_STRIP_MODULES | Remove modules from courses names | Maths [DPAMAT2D] -> Maths |
| COURSE_STRIP_CATEGORY | Remove category from course names | Maths CM -> Maths |
| COURSE_STRIP_PUNCTUATION | Remove ".,:;!?" from text | Math. -> Math |
| COURSE_GROUP_SIMILAR | Search for all event names and group ones containing another | Maths, Maths S1 -> Maths |
| COURSE_STRIP_REDUNDANT | Extract parts removed by the previous filter and remove them from all other courses | Physics S1 -> Physics |
| ROOMS_STRIP_AFTER_NUMBER | Remove all text after the first number found | Room 403 32 seats -> Room 403 |
| SITES_REMOVE_DUPLICATES | Remove duplicates from the list | Building A, Building A -> Building A |
