# i18n message namespaces

One namespace file = one owning pebble per wave. Feature pebbles add keys only to their assigned namespace under `messages/{locale}/{namespace}.json`.

| Namespace       | Owning pebble (wave)   |
| --------------- | ---------------------- |
| `common`        | M02-P02 (shared shell) |
| `auth`          | M04-P01                |
| `catalog`       | M05-P01                |
| `search`        | M05-P02                |
| `checkout`      | M07-P01                |
| `orders`        | M07-P02                |
| `vendor`        | M06-P01                |
| `admin`         | M08-P01                |
| `events`        | M09-P01                |
| `services`      | M10-P01                |
| `supplies`      | M11-P01                |
| `directory`     | M12-P01                |
| `legal`         | M15-P02                |
| `notifications` | M13-P01                |
| `account`       | M04-P06                |
| `ai`            | M14-P01                |

Skeleton keys use ICU message shape (`{variable}`). Translations beyond English land in later pebbles.
