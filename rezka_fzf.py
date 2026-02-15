#! /usr/bin/env python3

import os
import json
import subprocess
import sys
import signal
import platform
from HdRezkaApi import HdRezkaSession

"""
HDRezka FZF - Terminal User Interface for HDRezka streaming service

Features:
    - Search and browse HDRezka content from terminal
    - Watch movies and series with various video players
    - Clean terminal interface built on fzf
"""


class Config:
    def __init__(self):
        system = platform.system()
        
        if system == 'Windows':
            appdata = os.getenv('APPDATA')
            self.config_dir = os.path.join(appdata, 'hdrezka-tui')
        elif system == 'Darwin':
            home = os.path.expanduser('~')
            self.config_dir = os.path.join(home, 'Library', 'Application Support', 'hdrezka-tui')
        else:
            home = os.path.expanduser('~')
            self.config_dir = os.path.join(home, '.config', 'hdrezka-tui')
        
        self.config_path = os.path.join(self.config_dir, 'config.json')
        self._cache = None
        self.setup_config()
    
    def setup_config(self):
        if not os.path.exists(self.config_path):
            print('First run setup\n')
            
            url = input('Enter HDRezka URL [https://hdrezka.ag]: ').strip()
            username = input('Username (optional): ').strip()
            password = input('Password (optional): ').strip()
            
            config_data = {
                'url': url or 'https://hdrezka.ag',
                'username': username,
                'password': password,
                'player': 'auto'
            }
            
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            
            print(f'\nConfiguration saved to: {self.config_path}\n')
    
    def _load_cache(self):
        if self._cache is None:
            try:
                with open(self.config_path) as f:
                    self._cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._cache = {}
        return self._cache
    
    def load(self, key, default=None):
        return self._load_cache().get(key, default)


class FzfSelector:
    def __init__(self):
        self.available = self._check_fzf()
    
    def _check_fzf(self):
        try:
            result = subprocess.run(['which', 'fzf'], capture_output=True, timeout=1)
            return result.returncode == 0
        except:
            return False
    
    def select(self, items, prompt='Select', multi=False):
        if not self.available or not items:
            return None
        
        display_items = []
        value_map = {}
        
        for item in items:
            if isinstance(item, dict) and 'display' in item:
                display = item['display']
                value_map[display] = item.get('value', item)
            else:
                display = str(item)
                value_map[display] = item
            display_items.append(display)
        
        fzf_cmd = [
            'fzf',
            '--height=40%',
            '--layout=reverse',
            '--border=rounded',
            '--prompt=' + prompt + ' > ',
            '--pointer=>',
            '--ansi'
        ]
        
        if multi:
            fzf_cmd.append('--multi')
        
        try:
            process = subprocess.Popen(
                fzf_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, 'TERM': 'xterm-256color'}
            )
            
            input_text = '\n'.join(display_items)
            stdout, _ = process.communicate(input=input_text)
            
            if process.returncode != 0:
                return None
            
            selected_displays = stdout.strip().split('\n')
            
            if multi:
                return [value_map[d] for d in selected_displays if d in value_map]
            else:
                return value_map.get(selected_displays[0]) if selected_displays[0] else None
        
        except Exception:
            return None


class Player:
    def __init__(self, player_name=None):
        self.available_players = {
            'mpv': ['mpv', '--title={title}', '{url}'],
            'vlc': ['vlc', '{url}'],
            'iina': ['iina', '{url}'],
            'celluloid': ['celluloid', '{url}']
        }
        self.player_name = player_name or self._detect_player()
    
    def _detect_player(self):
        for player in ['mpv', 'vlc', 'iina', 'celluloid']:
            try:
                result = subprocess.run(['which', player], capture_output=True, timeout=1)
                if result.returncode == 0:
                    return player
            except:
                continue
        return 'mpv'
    
    def play(self, url, title=''):
        cmd_template = self.available_players.get(self.player_name, self.available_players['mpv'])
        cmd = [arg.format(title=title, url=url) for arg in cmd_template]
        
        try:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except:
            return False


class HdRezkaApp:
    def __init__(self):
        self.config = Config()
        self.session = None
        self.current_content = None
        self.fzf = FzfSelector()
        self.player = Player(self.config.load('player'))
    
    def setup(self):
        url = self.config.load('url', 'https://hdrezka.ag')
        username = self.config.load('username', '')
        password = self.config.load('password', '')
        
        try:
            self.session = HdRezkaSession(url)
            if username and password:
                self.session.login(username, password)
            return True
        except Exception as e:
            print(f'Connection error: {e}')
            return False
    
    def get_search_query(self):
        try:
            print('Search: ', end='', flush=True)
            query = input().strip()
            return query
        except (KeyboardInterrupt, EOFError):
            print('\nGoodbye!')
            sys.exit(0)
    
    def search_and_select(self):
        query = self.get_search_query()
        if not query:
            return None
        
        try:
            search_obj = self.session.search(query)
            results = []
            
            try:
                for page in search_obj:
                    if isinstance(page, list):
                        results.extend(page)
                    else:
                        results.append(page)
                    if len(results) >= 50:
                        break
            except StopIteration:
                pass
            
            if not results:
                print('No results found')
                return None
            
            result_items = []
            for item in results:
                title = item['title']
                extras = []
                if 'year' in item:
                    extras.append(str(item['year']))
                if 'type' in item:
                    content_type = item['type'].replace('format.', '').replace('_', ' ').title()
                    extras.append(content_type)
                
                display = f'{title}' + (f' [{', '.join(extras)}]' if extras else '')
                result_items.append({'display': display, 'value': item})
            
            return self.fzf.select(result_items, prompt='Select Content')
        
        except Exception as e:
            print(f'Search error: {e}')
            return None
    
    def load_content(self, item):
        try:
            self.current_content = self.session.get(item['url'].split('/')[-1])
            return True
        except Exception as e:
            print(f'Error loading content: {e}')
            return False

    def is_series(self):
        try:
            if hasattr(self.current_content, 'seriesInfo'):
                try:
                    series_info = self.current_content.seriesInfo
                    if series_info is not None:
                        return True
                except Exception:
                    pass
        
            if hasattr(self.current_content, 'episodesInfo'):
                try:
                    episodes = self.current_content.episodesInfo
                    if episodes and len(episodes) > 0:
                        return True
                except Exception:
                    pass
        
            if hasattr(self.current_content, 'type'):
                try:
                    content_type = str(self.current_content.type).lower()
                    if any(x in content_type for x in ['series', 'tvshow', 'сериал']):
                        return True
                except:
                    pass
        
            return False
        except Exception:
            return False
    
    def get_movie_translations(self):
        translations = []
        
        try:
            if hasattr(self.current_content, 'translators_names') and self.current_content.translators_names:
                for name, data in self.current_content.translators_names.items():
                    premium = ' [PREMIUM]' if data.get('premium', False) else ''
                    translations.append({
                        'display': f'{name}{premium}',
                        'value': data['id']
                    })
                return translations
            
            if hasattr(self.current_content, 'translators') and self.current_content.translators:
                for trans_id, data in self.current_content.translators.items():
                    name = data.get('name', 'Unknown')
                    premium = ' [PREMIUM]' if data.get('premium', False) else ''
                    translations.append({
                        'display': f'{name}{premium}',
                        'value': trans_id
                    })
                return translations
            
            return translations
        except Exception as e:
            print(f'Error getting translations: {e}')
            return translations
    
    def get_series_translations_from_seriesInfo(self, season, episode):
        translations = []
        try:
            if hasattr(self.current_content, 'seriesInfo'):
                series_info = self.current_content.seriesInfo
                if hasattr(self.current_content, 'translators'):
                    for tid, tdata in self.current_content.translators.items():
                        translations.append({
                            'translator_id': tid,
                            'translator_name': tdata.get('name', 'Unknown'),
                            'premium': tdata.get('premium', False)
                        })
        except:
            pass
        return translations

    def get_series_translations(self, season_num, episode_num):
        translations = []
    
        try:
            if hasattr(self.current_content, 'episodesInfo'):
                try:
                    episodes_info = self.current_content.episodesInfo
                    for season in episodes_info:
                        if season['season'] == season_num:
                            for episode in season['episodes']:
                                if episode['episode'] == episode_num:
                                    for trans in episode.get('translations', []):
                                        name = trans.get('translator_name', 'Unknown')
                                        premium = ' [PREMIUM]' if trans.get('premium', False) else ''
                                        translations.append({
                                            'display': f'{name}{premium}',
                                            'value': trans.get('translator_id')
                                        })
                                    break
                            break
                except:
                    pass
        
            if not translations and hasattr(self.current_content, 'translators'):
                for tid, tdata in self.current_content.translators.items():
                    name = tdata.get('name', 'Unknown')
                    premium = ' [PREMIUM]' if tdata.get('premium', False) else ''
                    translations.append({
                        'display': f'{name}{premium}',
                        'value': tid
                    })
        
            return translations
        except Exception as e:
            print(f'Error getting series translations: {e}')
            return translations
    
    def show_content_menu(self):
        content = self.current_content
        content_type = 'Series' if self.is_series() else 'Movie'
        
        menu_items = [
            {'display': f'Title: {content.name}', 'value': None},
            {'display': f'Original: {content.origName}', 'value': None},
        ]
        
        if hasattr(content, 'description') and content.description:
            desc = content.description[:150] + '...' if len(content.description) > 150 else content.description
            menu_items.append({'display': f'Description: {desc}', 'value': None})
        
        menu_items.extend([
            {'display': f'Year: {content.releaseYear}', 'value': None},
            {'display': f'Type: {content_type}', 'value': None},
            {'display': f'Rating: {content.rating}', 'value': None},
        ])
        
        menu_items.append({'display': '━━━ Available Actions ━━━', 'value': None})
        
        if hasattr(content, 'otherParts') and content.otherParts:
            menu_items.append({
                'display': f'View Other Parts ({len(content.otherParts)} available)',
                'value': 'other_parts'
            })
        
        menu_items.append({'display': 'Watch', 'value': 'watch'})
        
        return self.fzf.select(menu_items, prompt=f'{content_type} Menu')
    
    def handle_other_parts(self):
        parts = self.current_content.otherParts
        if not parts:
            return False
        
        parts_items = []
        for part in parts:
            for name, url in part.items():
                parts_items.append({'display': name, 'value': url})
        
        selected_url = self.fzf.select(parts_items, prompt='Select Part')
        
        if selected_url:
            try:
                self.current_content = self.session.get(selected_url.split('/')[-1])
                return True
            except:
                return False
        return False
    
    def select_episode(self):
        try:
            episodes_info = None
        
            if hasattr(self.current_content, 'episodesInfo'):
                try:
                    episodes_info = self.current_content.episodesInfo
                except Exception:
                    pass
        
            if not episodes_info and hasattr(self.current_content, 'seriesInfo'):
                try:
                    series_info = self.current_content.seriesInfo
                    if series_info and isinstance(series_info, dict):
                        episodes_info = []
                        for season_num, episodes in series_info.items():
                            if isinstance(episodes, (list, tuple)):
                                episode_list = []
                                for ep_num in episodes:
                                    episode_list.append({
                                        'episode': int(ep_num) if str(ep_num).isdigit() else ep_num,
                                        'translations': []
                                    })
                            
                                episodes_info.append({
                                    'season': int(season_num) if str(season_num).isdigit() else season_num,
                                    'episodes': episode_list
                                })
                except Exception:
                    pass
        
            if not episodes_info:
                print('This content doesnt have episodes')
                return None, None
        
            if len(episodes_info) == 1:
                season = episodes_info[0]
            else:
                season_items = []
                for s in episodes_info:
                    if isinstance(s, dict) and s.get('episodes'):
                        display = f'Season {s.get('season', '?')} ({len(s['episodes'])} episodes)'
                        season_items.append({'display': display, 'value': s})
            
                if not season_items:
                    print('No seasons available')
                    return None, None
            
                season = self.fzf.select(season_items, prompt='Season')
                if not season:
                    return None, None
        
            season_num = season.get('season')
            if season_num is None:
                print('Invalid season data')
                return None, None
        
            episodes = season.get('episodes', [])
            if not episodes:
                print(f'No episodes for season {season_num}')
                return None, None
        
            episode_items = []
            for e in episodes:
                ep_num = e.get('episode')
                if ep_num:
                    episode_items.append({'display': f'Episode {ep_num}', 'value': e})
        
            if not episode_items:
                print('No episodes available')
                return None, None
        
            episode = self.fzf.select(episode_items, prompt=f'S{season_num} Episode')
            if not episode:
                return None, None
        
            episode_num = episode.get('episode')
        
            return season_num, episode_num
        
        except Exception as e:
            print(f'Error selecting episode: {e}')
            return None, None
    
    def play_content(self, season=None, episode=None):
        try:
            translator_id = None
            max_retries = 3
            retry_count = 0
        
            is_series_content = False
            try:
                is_series_content = self.is_series()
            except Exception as e:
                print(f'Warning: Could not determine content type: {e}')
                is_series_content = season is not None and episode is not None
        
            while retry_count < max_retries:
                try:
                    if is_series_content:
                        if season is not None and episode is not None:
                            translations = self.get_series_translations(season, episode)
                        else:
                            print('This is a series. Please select episode first.')
                            return
                    else:
                        translations = self.get_movie_translations()
                
                    if translations:
                        if len(translations) == 1:
                            translator_id = translations[0]['value']
                            trans_name = translations[0].get('display', 'Unknown')
                            print(f'Using translation: {trans_name}')
                        else:
                            prompt = 'Select Translation'
                            if season and episode:
                                prompt = f'S{season}E{episode} Translation'
                        
                            selected = self.fzf.select(translations, prompt=prompt)
                            if selected:
                                translator_id = selected
                            else:
                                return
                    else:
                        print('No translations available')
                        translator_id = None
                
                    if is_series_content and season is not None and episode is not None:
                        stream = self.current_content.getStream(
                            season=season,
                            episode=str(episode),
                            translation=translator_id
                        )
                    else:
                        if translator_id:
                            stream = self.current_content.getStream(translation=translator_id)
                        else:
                            stream = self.current_content.getStream()
                    break
                
                except UnicodeDecodeError as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f'\n⚠️  Decoding error, retrying... ({retry_count}/{max_retries})')
                        continue
                    else:
                        print(f'\n❌ Failed after {max_retries} attempts: {e}')
                        return
                except Exception as e:
                    print(f'Error getting stream: {e}')
                    import traceback
                    traceback.print_exc()
                    return
        
            qualities = ['2160', '1080 Ultra', '1080', '720', '480', '360']
            available = []
            for q in qualities:
                try:
                    stream(q)
                    available.append(q)
                except:
                    pass
        
            if not available:
                print('No qualities available')
                return
        
            quality_items = [{'display': f'{q}p', 'value': q} for q in available]
            quality = self.fzf.select(quality_items, prompt='Quality')
        
            if not quality:
                return
        
            urls = stream(quality)
        
            if isinstance(urls, bytes):
                try:
                    urls = urls.decode('utf-8', errors='ignore')
                except:
                    urls = str(urls)
        
            if isinstance(urls, str):
                if urls.strip().startswith('['):
                    try:
                        urls = json.loads(urls)
                    except:
                        urls = [urls]
                else:
                    urls = [urls]
        
            if isinstance(urls, list):
                if len(urls) == 1:
                    url = urls[0]
                else:
                    url_items = [{'display': str(u)[:132], 'value': u} for u in urls]
                    url = self.fzf.select(url_items, prompt='Select URL')
            else:
                url = urls
        
            if url:
                title = self.current_content.name
                if season and episode:
                    title += f' S{season}E{episode}'
                self.player.play(url, title)
    
        except Exception as e:
            print(f'Playback error: {e}')
            import traceback
            traceback.print_exc()
    
    def run(self):
        if not self.setup():
            return
        
        if not self.fzf.available:
            print('fzf not found. Please install fzf')
            return
        
        def sigint_handler(sig, frame):
            print('\nGoodbye!')
            sys.exit(0)
        
        signal.signal(signal.SIGINT, sigint_handler)
        
        while True:
            try:
                item = self.search_and_select()
                if not item:
                    continue
                
                if not self.load_content(item):
                    continue
                
                while True:
                    action = self.show_content_menu()
                    
                    if not action or action is None:
                        break
                    
                    if action == 'other_parts':
                        self.handle_other_parts()
                        continue
                    
                    if action == 'watch':
                        if self.is_series():
                            season, episode = self.select_episode()
                            if season and episode:
                                self.play_content(season, episode)
                        else:
                            self.play_content()
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f'Error: {e}')
                continue


def main():
    app = HdRezkaApp()
    app.run()


if __name__ == '__main__':
    main()
