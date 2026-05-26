select * from {{ source('bronze', 'raw_ls2') }}
