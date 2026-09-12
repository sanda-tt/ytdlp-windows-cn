"""Bounded static analysis of common player configuration; never executes JS."""
import base64
import html
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

MAX_TEXT = 2_000_000
STRING = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`'''
MEDIA = re.compile(r'\.(?:m3u8|mpd|mp4|webm|m4v|mov)(?:[?#]|$)', re.I)


def decode_string(token):
    raw = token[1:-1]
    def repl(m):
        code = m.group(1)
        if code.startswith(('u', 'x')):
            return chr(int(code[1:], 16))
        return {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f'}.get(code, code)
    return re.sub(r'\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', repl, raw)


def http_url(value, base):
    if not isinstance(value, str):
        return None
    try:
        result = urljoin(base, value)
        parsed = urlsplit(result)
        parsed.port  # Reject malformed ports rather than crashing the fallback.
    except ValueError:
        return None
    return result if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username else None


def media_url(value, base):
    if not isinstance(value, str) or len(value) > 16000:
        return None
    value = html.unescape(value.strip()).replace('\\/', '/')
    if not MEDIA.search(value) or any(c in value for c in '\n\r<>"\'{}'):
        return None
    return http_url(value, base)


class Page(HTMLParser):
    def __init__(self, text, url):
        super().__init__(convert_charrefs=True)
        self.url, self.base = url, url
        self.elements, self.scripts, self.external, self.frames = [], [], [], []
        self.direct, self.title = [], ''
        self.in_script = self.in_title = False
        self.feed(text[:MAX_TEXT])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == 'base' and attrs.get('href'):
            self.base = http_url(attrs['href'], self.url) or self.base
        if tag in ('video', 'source'):
            self.direct.extend(attrs.get(k, '') for k in ('src', 'data-src'))
        if tag == 'meta' and (attrs.get('property') or '').startswith('og:video'):
            self.direct.append(attrs.get('content', ''))
        if tag == 'iframe' and attrs.get('src'):
            frame = http_url(attrs['src'], self.base)
            if frame:
                self.frames.append(frame)
        if tag == 'script':
            self.in_script = True
            if attrs.get('src'):
                script = http_url(attrs['src'], self.base)
                if script:
                    self.external.append(script)
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)
        if self.in_title:
            self.title += data

    def select(self, selector):
        for tag, attrs in self.elements:
            if selector == tag or selector == '#' + (attrs.get('id') or ''):
                return attrs
            if selector.startswith('.') and selector[1:] in (attrs.get('class') or '').split():
                return attrs
        raise ValueError('Unknown DOM selector')


class Expression:
    """Whitelist interpreter for literals, +, templates, DOM data and decoding."""
    TOKEN = re.compile(r'\s*(?:(?P<string>' + STRING + r')|(?P<name>[\w$]+)|(?P<op>[^\s]))', re.S)

    def __init__(self, text, env, page, depth=0):
        if depth > 12:
            raise ValueError('Expression recursion limit')
        self.tokens = []
        self.line_breaks = []
        for m in self.TOKEN.finditer(text[:20000]):
            self.tokens.append((m.lastgroup, m.group(m.lastgroup)))
            self.line_breaks.append('\n' in text[m.start():m.start(m.lastgroup)])
            if len(self.tokens) >= 1500:
                break
        self.pos, self.env, self.page, self.depth = 0, env, page, depth
        self.nesting = 0

    def peek(self, value):
        return self.pos < len(self.tokens) and self.tokens[self.pos][1] == value

    def take(self):
        if self.pos >= len(self.tokens):
            raise ValueError('Incomplete expression')
        result = self.tokens[self.pos]
        self.pos += 1
        return result

    def require(self, value):
        if self.take()[1] != value:
            raise ValueError('Unexpected token')

    def evaluate(self):
        self.nesting += 1
        try:
            if self.nesting > 24:
                raise ValueError('Expression nesting limit')
            return self._evaluate()
        finally:
            self.nesting -= 1

    def _evaluate(self):
        value = self.atom()
        while self.peek('+'):
            self.take()
            other = self.atom()
            if not isinstance(value, (str, int)) or not isinstance(other, (str, int)):
                raise ValueError('Unsupported concatenation')
            value = value + other if isinstance(value, int) and isinstance(other, int) else str(value) + str(other)
            if len(str(value)) > 20000:
                raise ValueError('Value limit')
        # Never accept a partly evaluated expression as a complete stream URL.
        if self.pos < len(self.tokens) and self.tokens[self.pos][1] not in (';', ',', ')', '}', ']'):
            # Common JS automatic semicolon insertion: a new statement name.
            if not (self.line_breaks[self.pos] and self.tokens[self.pos][0] == 'name'):
                raise ValueError('Unsupported expression operator')
        return value

    def atom(self):
        kind, token = self.take()
        if kind == 'string':
            value = decode_string(token)
            if token.startswith('`'):
                value = re.sub(r'\$\{([^{}]+)\}', lambda m: str(Expression(m[1], self.env, self.page, self.depth + 1).evaluate()), value)
        elif token == '(':
            value = self.evaluate()
            self.require(')')
        elif token.isdecimal():
            value = int(token)
        elif token in ('atob', 'decodeURIComponent', 'decodeURI', 'unescape', 'String'):
            self.require('(')
            arg = self.evaluate()
            self.require(')')
            if not isinstance(arg, (str, int)):
                raise ValueError('Unsupported decoding argument')
            value = (base64.b64decode(str(arg), validate=True).decode('utf-8') if token == 'atob'
                     else str(arg) if token == 'String' else unquote(str(arg)))
        elif token == 'document':
            self.require('.')
            method = self.take()[1]
            if method not in ('querySelector', 'getElementById'):
                raise ValueError('Unsupported DOM access')
            self.require('(')
            selector = self.evaluate()
            self.require(')')
            value = self.page.select(('#' if method == 'getElementById' else '') + selector)
        elif token in self.env:
            value = self.env[token]
        else:
            raise ValueError('Unknown variable')
        while self.peek('.') or self.peek('['):
            if self.peek('['):
                self.take()
                prop = self.evaluate()
                self.require(']')
            else:
                self.take()
                prop = self.take()[1]
            if not isinstance(value, dict):
                raise ValueError('Unsupported property access')
            if prop == 'dataset':
                value = {re.sub(r'-([a-z])', lambda m: m[1].upper(), k[5:]): v for k, v in value.items() if k.startswith('data-')}
            elif prop == 'getAttribute':
                self.require('(')
                attr = self.evaluate()
                self.require(')')
                value = value[attr]
            else:
                value = value[prop]
        return value


def discover(page, extra_scripts=()):
    candidates, env = {}, {}
    def add(value, score):
        result = media_url(value, page.base)
        if result:
            candidates[result] = max(score, candidates.get(result, 0))
    for value in page.direct:
        add(value, 100)
    for _, attrs in page.elements:
        for key, value in attrs.items():
            if key.startswith('data-'):
                add(value, 70)
    scripts = '\n'.join([*page.scripts, *extra_scripts])[:MAX_TEXT]
    assignments = list(re.finditer(r'(?<![\w$.])([a-zA-Z_$][\w$]*)\s*=(?!=|>)', scripts))[:500]
    # Several passes allow configuration values declared in a later script block.
    for _ in range(3):
        for match in assignments:
            try:
                env[match[1]] = Expression(scripts[match.end():match.end() + 20000], env, page).evaluate()
            except (ValueError, KeyError, TypeError, UnicodeError):
                continue
    for match in re.finditer(r'''(?:\b(?:url|src|file|source|playUrl|videoUrl|hls|dash)\b["']?\s*:|\.loadSource\s*\()''', scripts, re.I):
        try:
            add(Expression(scripts[match.end():match.end() + 20000], env, page).evaluate(), 95)
        except (ValueError, KeyError, TypeError, UnicodeError):
            pass
    for value in env.values():
        add(value, 80)
    for match in re.finditer(STRING, scripts):
        value = decode_string(match[0])
        add(value, 30)
        # URL-encoded or base64 literal player payloads. No eval or JS execution.
        add(unquote(value), 25)
        if len(value) < 32000:
            try:
                add(base64.b64decode(value, validate=True).decode('utf-8'), 20)
            except (ValueError, UnicodeError):
                pass
    return sorted(candidates.items(), key=lambda item: -item[1])[:16]
