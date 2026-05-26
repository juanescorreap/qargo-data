{{ config(materialized='view') }}

select * from {{ ref('stg_par2') }}
union all
select * from {{ ref('stg_ls2') }}
