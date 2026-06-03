import json
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class HLTVMatchesParser:
    """Парсер матчей HLTV.org (live + upcoming) с логотипами команд."""

    def __init__(self, headless: bool = True, timeout: int = 30, debug: bool = False):
        self.headless = headless
        self.timeout = timeout * 1000
        self.debug = debug
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        self.page = context.new_page()

    def fetch_page(self, url: str = "https://www.hltv.org/matches") -> None:
        if not self.page:
            self.start()
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_selector(
                "div.match-wrapper[data-match-id]",
                state="attached",
                timeout=self.timeout,
            )
        except PlaywrightTimeout:
            print("[WARNING] Матчи не появились за отведённое время.")
            return
        self.page.wait_for_timeout(5000)
        if self.debug:
            stats = self.page.evaluate("""() => {
                const wrappers = document.querySelectorAll('.match-wrapper');
                let liveCount = 0, upcomingCount = 0;
                wrappers.forEach(w => {
                    if (w.getAttribute('live') === 'true') liveCount++;
                    else upcomingCount++;
                });
                return {total: wrappers.length, live: liveCount, upcoming: upcomingCount};
            }""")
            print(f"[DEBUG] Всего матчей: {stats['total']}, live: {stats['live']}, upcoming: {stats['upcoming']}")

    def parse_matches(self) -> List[Dict]:
        if not self.page:
            return []
        matches = self.page.evaluate(r"""() => {
            const wrappers = document.querySelectorAll('.match-wrapper');
            const result = [];
            wrappers.forEach(wrapper => {
                const matchId = wrapper.getAttribute('data-match-id');
                if (!matchId) return;
                const stars = parseInt(wrapper.getAttribute('data-stars')) || 0;
                const live = wrapper.getAttribute('live') === 'true';
                const eventId = wrapper.getAttribute('data-event-id');
                let time = '';
                const timeEl = wrapper.querySelector('.matchTime') ||
                               wrapper.querySelector('.match-info .time') ||
                               wrapper.querySelector('[class*="time"]');
                if (timeEl) {
                    time = timeEl.innerText.trim();
                } else if (live) {
                    time = 'LIVE';
                }
                const team1El = wrapper.querySelector('.team1');
                let team1 = '', team1Logo = null;
                if (team1El) {
                    const nameEl = team1El.querySelector('.matchTeamName') || team1El;
                    team1 = nameEl.innerText.trim();
                    const logoImg = team1El.querySelector('img');
                    if (logoImg) team1Logo = logoImg.src;
                }
                const team2El = wrapper.querySelector('.team2');
                let team2 = '', team2Logo = null;
                if (team2El) {
                    const nameEl = team2El.querySelector('.matchTeamName') || team2El;
                    team2 = nameEl.innerText.trim();
                    const logoImg = team2El.querySelector('img');
                    if (logoImg) team2Logo = logoImg.src;
                }
                let eventName = '';
                const eventEl = document.querySelector(`.match-event[data-event-id="${eventId}"]`);
                if (eventEl) {
                    eventName = eventEl.getAttribute('data-event-headline') ||
                                eventEl.innerText.trim();
                } else {
                    const innerEvent = wrapper.querySelector('.matchEventName');
                    if (innerEvent) eventName = innerEvent.innerText.trim();
                }
                let date = '';
                function findDate(el) {
                    let current = el;
                    while (current && current !== document.body) {
                        if (current.hasAttribute && current.hasAttribute('data-day')) {
                            return current.getAttribute('data-day').trim();
                        }
                        const headlines = current.querySelectorAll('[class*="day"], [class*="headline"], h2, h3, h4');
                        for (const h of headlines) {
                            const text = h.innerText.trim();
                            if (/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow)\b/i.test(text) ||
                                /\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i.test(text) ||
                                /\d{1,2}\/\d{1,2}/.test(text)) {
                                return text;
                            }
                        }
                        current = current.parentElement;
                    }
                    return '';
                }
                date = findDate(wrapper);
                if (!date) {
                    let prev = wrapper.previousElementSibling;
                    while (prev) {
                        if (!prev.classList.contains('match-wrapper')) {
                            const text = prev.innerText.trim();
                            if (text && /\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow)\b/i.test(text)) {
                                date = text;
                                break;
                            }
                        }
                        prev = prev.previousElementSibling;
                    }
                }
                result.push({
                    id: matchId,
                    date: date,
                    time: time,
                    team1: team1,
                    team2: team2,
                    team1Logo: team1Logo,
                    team2Logo: team2Logo,
                    event: eventName,
                    eventId: eventId,
                    stars: stars,
                    live: live,
                    url: 'https://www.hltv.org/matches/' + matchId
                });
            });
            return result;
        }""")
        return matches

    def fetch_match_details(self, match_url: str) -> dict:
        """
        Загружает страницу конкретного матча и возвращает составы команд и карты.
        """
        if not self.page:
            self.start()
        self.page.goto(match_url, wait_until="domcontentloaded")
        # Ждём загрузки контента
        self.page.wait_for_timeout(5000)

        # Выполняем поиск составов и карт
        details = self.page.evaluate("""() => {
            const lineups = { team1: [], team2: [] };

            // Ищем контейнеры с игроками (подходят под разные классы)
            const teamContainers = document.querySelectorAll('.team-left, .team-right, .lineup, [class*="team1"] [class*="player"], [class*="team2"] [class*="player"]');
            let team1Players = [];
            let team2Players = [];

            // Простой способ: найти две группы игроков по соседству с заголовками команд
            const allPlayers = document.querySelectorAll('.player, [class*="player"]');
            const playersArray = Array.from(allPlayers).filter(p => p.innerText.trim().length > 0);

            // Если нашли 10 игроков, делим пополам
            if (playersArray.length === 10) {
                team1Players = playersArray.slice(0, 5);
                team2Players = playersArray.slice(5, 10);
            } else {
                // Ищем игроков внутри контейнеров команд
                const containers = document.querySelectorAll('.standard-box, .lineup, .team-lineup');
                containers.forEach(container => {
                    const header = container.querySelector('h2, h3, .heading');
                    if (header) {
                        const headerText = header.innerText.toLowerCase();
                        const players = container.querySelectorAll('.player');
                        if (headerText.includes('team1') || headerText.includes('thunder') || headerText.includes('home')) {
                            team1Players = Array.from(players);
                        } else if (headerText.includes('team2') || headerText.includes('flyquest') || headerText.includes('away')) {
                            team2Players = Array.from(players);
                        }
                    }
                });
            }

            function extractPlayers(elements) {
                return elements.map(el => ({
                    nick: el.querySelector('.nick, .playerNickname, .name, .text-ellipsis')?.innerText.trim() || '',
                    name: el.querySelector('.realname, .playerRealname, .small')?.innerText.trim() || '',
                    photo: el.querySelector('img')?.src || ''
                }));
            }

            lineups.team1 = extractPlayers(team1Players);
            lineups.team2 = extractPlayers(team2Players);

            // Карты
            const maps = [];
            const mapBlocks = document.querySelectorAll('.veto-box .veto-map, .map-container .map, .map-holder .map, .map');
            mapBlocks.forEach(m => {
                const mapName = m.querySelector('.map-name, .mapName, .bold')?.innerText.trim() || m.innerText.split('\\n')[0].trim();
                const pickInfo = m.querySelector('.pick, .ban, .status, .result')?.innerText.trim() || '';
                const statsText = m.querySelector('.map-stats, .stats')?.innerText.trim() || '';
                maps.push({
                    name: mapName,
                    pick: pickInfo,
                    stats: statsText.replace(/\\s+/g, ' ')
                });
            });
            return { lineups, maps };
        }""")
        return details

    def get_matches(self, url: str = "https://www.hltv.org/matches") -> List[Dict]:
        self.fetch_page(url)
        return self.parse_matches()

    def close(self):
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()