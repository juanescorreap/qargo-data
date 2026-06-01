select
    source_name,
    filename,
    row_count,
    loaded_at
from ingestion.processed_files
order by loaded_at desc
