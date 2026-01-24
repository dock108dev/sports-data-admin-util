
### Routers/Endpoints - Needs Review

| File | LOC | Recommendation |
|------|-----|----------------|
| admin/pbp.py | 876 | Consider splitting by operation type |
| admin/pipeline/endpoints.py | 716 | Consider splitting pipeline stages |
| sports/games.py | 606 | Review - multiple game operations |
| game_snapshots.py | 606 | Review - snapshot logic |


### Services

| File | LOC | Recommendation |
|------|-----|----------------|
| timeline_generator.py | 774 | Review - timeline generation |

### Scraper

| File | LOC | Recommendation |
|------|-----|----------------|
| run_manager_helpers.py | 636 | Already split from run_manager |
| jobs/tasks.py | 548 | Review - Celery task definitions |
