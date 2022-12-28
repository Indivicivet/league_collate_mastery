from collections import defaultdict
from datetime import datetime
import urllib.request
import urllib.parse
import re
import sys
from pathlib import Path


def load_summoner_page(username, region="EUW"):
    BASE_URL = "https://championmastery.gg/summoner?"
    target_url = BASE_URL + urllib.parse.urlencode({
        "region": region,
        "summoner": user_euw,
    })
    print(f"loading {target_url} ...")
    result = urllib.request.urlopen(target_url)
    return result.read().decode("utf-8")  # assumptions


def get_pre_rows_post(webpage):
    """Takes a https://championmastery.gg/ lookup
    page and returns the stuff before, table in the middle, and stuff after"""
    pre_table, table_and_post = webpage.split('<tbody id="tbody">')
    table, post_table = table_and_post.split("</tbody>")
    return pre_table, table, post_table


def get_stripped_table_rows(webpage):
    _, result, _ = get_pre_rows_post(webpage)
    regexes_to_kill = [
        # simple strs
        "\t",  # must kill tab first
        "<td data-value=\"0\">",
        '<img src="/img/chest.png" class="chest( notEarned)?">',
        '<div class="progressBar-outer">',
        "<tr>",
        "</tr>",
        "<td>",
        "</td>",
        "</div>",
        "</a>",
        # regexes
        r"<td data-format-time=\"\d+\" data-value=\"\d+\" data-toggle=\"tooltip\">",
        r"<div class=\"progressBar-inner\" style=\"width: \d+(\.\d+)?\%\">",
        r"<td class=\"collapsible\" data-value=\"\d+(\.\d+)?\" data-tooltip=\"tooltip\" ",
        r"title=\"\d+/\d+ points \(\d+(\.\d+)?\%\)\">",
        r"<a href=\"\/champion\?champion=\d+\">",
        r"td( class=\"\")?( data-format-number=\"\d+\")? data-value=\"\d+\"",
        r"<img class=\"token( notEarned)?\" src=\"/img/token.png\">",
        ' data-tooltip="tooltip" title=',  # mastery token extra info
        r"<td class=\"collapsible\"  data-value=\"\d+\">",  # I probably stripped in bad order
        "N/A",
        "Mastered",
        "<>",
    ]
    for regex in regexes_to_kill:
        result = re.sub(regex, "", result)
    result = result.replace("&#x27;", "'").replace("&amp;", "&")
    return re.sub(r"\s\s+", "\n", result).strip().split("\n")  # kill multiple linebreaks


def get_mastery_scores(webpage):
    rows = get_stripped_table_rows(webpage)
    champ_chunks = [rows[i:i + 4] for i in range(0, len(rows), 4)]

    def count_total_tokens(progress_to_next):
        """n/3 -> 2+n, n/2 -> n"""
        if "Max level" in progress_to_next:
            return 5
        if "token" not in progress_to_next:
            return 0
        tok_have, tok_max = re.search(r"(\d)/(\d)", progress_to_next).groups()
        if tok_max == "3":  # already M6
            return 2 + int(tok_have)
        return int(tok_have)

    return {
        champ_name: (int(level), int(points), count_total_tokens(progress))
        for champ_name, level, points, progress in champ_chunks
    }


def combine_mastery_scores(*accounts):
    res = defaultdict(lambda: (0, 0, 0))
    for account in accounts:
        for champ_name, (level, points, tokens) in account.items():
            old_level, old_points, old_tokens = res[champ_name]
            res[champ_name] = (
                max(old_level, level),
                old_points + points,
                max(old_tokens, tokens),
            )
    return res


DISPLAY_VISUAL_DEFAULT = "-v" in sys.argv or "--visual" in sys.argv


def prettify_score_list(scores, display_visual=DISPLAY_VISUAL_DEFAULT):
    return "\n".join([
        f"{str(i + 1).ljust(4)} Lv{level} {champ.rjust(15)} {'X' * (points // 2000) or '.'}"
        if display_visual else
        f"{str(i + 1).ljust(4)} Lv{level} {champ.ljust(15)}  Points {str(points).ljust(7)} {'*' * tokens}"
        for i, (champ, (level, points, tokens)) in enumerate(sorted(
            scores.items(),
            key=lambda t: t[1][1],  # score
            reverse=True,
        ))
    ])


if __name__ == "__main__":
    USERNAMES_FILE = Path(__file__).parent / "usernames.txt"
    USERNAMES = (
        [
            x
            for x in USERNAMES_FILE.read_text().splitlines()
            if x and x[0] != "#"
        ]
        if USERNAMES_FILE.exists()
        else ["thebausffs"]  # example
    )
    OUT_FOLDER_CONFIG_FILE = Path(__file__).parent / "out_folder.txt"
    OUT_FOLDER = (
        Path(OUT_FOLDER_CONFIG_FILE.read_text().strip())
        if OUT_FOLDER_CONFIG_FILE.exists()
        else None
    )
    user_scores = {}
    for user_euw in USERNAMES:
        page = load_summoner_page(user_euw)
        user_scores[user_euw] = get_mastery_scores(page)
    combined_scores = combine_mastery_scores(*user_scores.values())
    total_points = sum(pts for _, pts, _ in combined_scores.values())
    account_points = [
        (acc, sum(points for _, points, _ in scores.values()))
        for acc, scores in user_scores.items()
    ]
    atleast_m = {
        x: sum(1 for level, _, _ in combined_scores.values() if level >= x)
        for x in range(1, 8)
    }
    atleast_m[7] = sum(1 for _, _, tokens in combined_scores.values() if tokens == 5)
    account_distribution_str = "\n".join(
        f"{acc: <20}{points: <10}{(1000 * points) // total_points / 10}%"
        for acc, points in sorted(account_points, key=lambda t: t[1], reverse=True)
    )
    champions_at_least_level_str = "\n".join(
        f"M{i}: {atleast_m[i]}"
        for i in reversed(range(1, 8))
    )
    levels_visualization_str = "".join(
        str(next(n for n in reversed(range(1, 8)) if atleast_m[n] >= i))
        + ("\n" if i % 10 == 0 else "")
        for i in range(1, atleast_m[1] + 1)
    )
    time_str = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")
    result_str = f"""{prettify_score_list(combined_scores)}

Total mastery: {total_points}

Per account:
{account_distribution_str}

Number of champions with each mastery level earned:
{champions_at_least_level_str}

This looks like:
{levels_visualization_str}

collated mastery as of {time_str}
"""
    print(result_str)
    if OUT_FOLDER is not None:
        time_str_windows = datetime.now().strftime("%Y-%m-%d_%Hh%M")
        OUT_FILE = OUT_FOLDER / f"collated_mastery_{time_str_windows}.txt"
        OUT_FILE.write_text(result_str)
        print(f"wrote to {OUT_FILE}")
