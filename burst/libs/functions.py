from config import settings


def calc_block_reward(height: int) -> int:
    if height >= settings.BLOCK_REWARD_LIMIT_HEIGHT:
        return settings.BLOCK_REWARD_LIMIT_AMOUNT
    month = int(height / 10800)
    return int(pow(0.95, month) * 10000)
