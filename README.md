# Celcat Calendar Scraper

An asynchronous Python library for scraping Celcat calendar systems.

## Installation

```sh
pip install celcat-scraper
```

## Usage

Basic example of retrieving calendar events:

```python
import asyncio
from datetime import date, timedelta
from celcat_scraper import CelcatConfig, CelcatScraperAsync

async def main():
    # Configure the scraper
    config = CelcatConfig(
        url="https://celcat.university.com",
        username="your_username",
        password="your_password",
        include_holidays=True
    )

    # Create scraper instance and get events
    async with CelcatScraperAsync(config) as scraper:

        start_date = date.today()
        end_date = start_date + timedelta(days=30)
        
        # Recommended to store events locally and reduce the amout of requests
        file_path = 'store.json'
        events = scraper.deserialize_events(file_path)
        
        events = await scraper.get_calendar_events(start_date, end_date, previous_events=events)
        
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

## Features

* Async/await support for better performance
* Rate limiting with adaptive backoff
* Optional caching support
* Automatic session management
* Batch processing of events
* Error handling and retries
