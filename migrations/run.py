"""Entrypoint for the migrations Job container.

Runs `prisma migrate deploy` against the LiteLLM writer database using the
recovery logic in `litellm_proxy_extras.ProxyExtrasDBManager.setup_database`
(P3005 baseline + P3009/P3018 idempotent-error handling, retries, etc.).

Env vars:
  DATABASE_URL                  required unless `IAM_TOKEN_DB_AUTH=true`
                                (in which case it is minted at startup)
  DIRECT_URL                    optional — used by `migrate diff` when the
                                primary URL is a pooler (e.g. Neon -pooler)
  USE_V2_MIGRATION_RESOLVER     "false" → fall back to the v1 resolver
                                (legacy diff-and-force recovery). Defaults
                                to "true": the v2 resolver avoids the schema
                                thrashing seen during rolling deploys when
                                two LiteLLM versions contend for the same DB.
  USE_PRISMA_DB_PUSH            "true" → use `prisma db push` instead of
                                `migrate deploy`. Default false.
"""

import os
import sys

from litellm.proxy.auth.rds_iam_token import init_iam_db_url_from_env
from litellm_proxy_extras._logging import logger
from litellm_proxy_extras.utils import ProxyExtrasDBManager, str_to_bool


def main() -> int:
    # Mint DATABASE_URL from IAM env vars when IAM_TOKEN_DB_AUTH is set,
    # matching the gateway/backend startup path. No-op when IAM auth is
    # disabled — preserves any DATABASE_URL the helm chart already set.
    init_iam_db_url_from_env()

    if not os.getenv("DATABASE_URL"):
        logger.error(
            "DATABASE_URL is not set and IAM_TOKEN_DB_AUTH did not mint one — "
            "cannot run migrations."
        )
        return 1

    # v2 is the safer default for componentized deploys: it skips the
    # diff-and-force recovery from v1 that caused schema thrashing during
    # rolling deploys. Set USE_V2_MIGRATION_RESOLVER=false to opt back into v1.
    use_v2 = str_to_bool(os.getenv("USE_V2_MIGRATION_RESOLVER", "true"))
    use_db_push = str_to_bool(os.getenv("USE_PRISMA_DB_PUSH"))

    logger.info(
        "Starting prisma migration job (use_migrate=%s, use_v2_resolver=%s)",
        not use_db_push,
        use_v2,
    )
    ok = ProxyExtrasDBManager.setup_database(
        use_migrate=not use_db_push,
        use_v2_resolver=use_v2,
    )
    if not ok:
        logger.error("Migration job failed after retries.")
        return 1
    logger.info("Migration job completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
