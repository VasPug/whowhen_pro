"""Experimental citation location, separate from claim support. Not enabled by default."""
import re

_QUOTES = str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"})


def normalized(text):
    """Matching view plus offsets into untouched source (no case/math/code rewriting)."""
    chars, starts, ends = [], [], []
    for i, ch in enumerate(text):
        ch = ' ' if ch.isspace() else ch.translate(_QUOTES)
        if ch == ' ' and chars and chars[-1] == ' ':
            ends[-1] = i+1
        else:
            chars.append(ch); starts.append(i); ends.append(i+1)
    return ''.join(chars), starts, ends


def _spans(needle, haystack):
    if not needle: return []
    out=[]
    numeric_tokens=[m.span() for m in re.finditer(
        r'(?<![\w.+−-])[+−-]?(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)(?:[eE][+−-]?\d+)?(?![\w]|[.,]\d)',haystack)]
    for m in re.finditer(re.escape(needle), haystack):
        a,b=m.span()
        if any(start<a<end or start<b<end for start,end in numeric_tokens):continue
        # Don't match the suffix of a number, identifier or signed literal.
        if a and needle[0].isalnum() and (haystack[a-1].isalnum() or haystack[a-1]=='_'):continue
        if a and needle[0].isdigit() and haystack[a-1] in '+-−.,':continue
        if b<len(haystack) and needle[-1].isalnum() and (haystack[b].isalnum() or haystack[b]=='_'):continue
        if b<len(haystack) and needle[-1].isdigit() and haystack[b] in '.,' and b+1<len(haystack) and haystack[b+1].isdigit():continue
        out.append((a,b))
    return out


def locate(ref, sources, policy='aliases'):
    """Locate evidence; even 'matched' proves copying/location, never claim truth."""
    if policy not in ('exact','normalized','aliases','ellipsis'):raise ValueError('Unknown policy')
    missing={'status':'unresolved'}
    if not isinstance(ref,dict):return missing
    key, quote=ref.get('ref'),ref.get('quote')
    if not isinstance(key,str) or not isinstance(quote,str) or not quote.strip():return missing
    alias=False
    if key not in sources and policy in ('aliases','ellipsis') and key in ('task:0','task:N') and 'task' in sources:
        key='task';alias=True
    if key not in sources:return missing
    source=sources[key]
    if policy=='exact':
        spans=_spans(quote,source); starts=list(range(len(source)));ends=list(range(1,len(source)+1))
    else:
        text,starts,ends=normalized(source); q=normalized(quote)[0].strip()
        spans=_spans(q,text)
    if len(spans)>1:return {'status':'ambiguous','ref':key,'matches':len(spans)}
    if spans:
        a,b=spans[0];a,b=starts[a],ends[b-1]
        return {'status':'matched','ref':key,'start':a,'end':b,'quote':source[a:b],
                'method':'alias' if alias else ('exact' if source[a:b]==quote else 'normalized')}
    if policy!='ellipsis' or not re.search(r'\.{3}|…',quote):return missing
    fragments=[normalized(x)[0].strip() for x in re.split(r'\.{3}|…',quote) if x.strip()]
    if not fragments or any(len(x)<12 for x in fragments):return missing
    positions=[]
    for fragment in fragments:
        matches=_spans(fragment,text)
        if len(matches)!=1:return {'status':'ambiguous' if matches else 'unresolved','ref':key}
        positions.append(matches[0])
    if any(a[1]>b[0] for a,b in zip(positions,positions[1:])):return missing
    # Give the checker the FULL event, restoring conditions omitted by the model.
    # Never promote the old shortened-quote verdict to a supported claim.
    return {'status':'located_needs_review','ref':key,'start':0,'end':len(source),
            'quote':source,'method':'ellipsis','alias':alias}
