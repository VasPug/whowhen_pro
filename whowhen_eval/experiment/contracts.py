"""Shared schema hints; deterministic validation remains required."""

def schema_for(kind, style, refs):
    def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    refprops={'ref':{'type':'string','enum':list(refs)}}
    if style=='quotes':refprops['quote']={'type':'string'}
    reference=obj(refprops)
    if kind=='requirements':
        body=obj({'requirements':{'type':'array','items':obj({'text':{'type':'string'},'source':reference})}})
    else:
        key,values=('verdict',['support','challenge','inconclusive']) if kind=='review' else ('result',['satisfied','violated','inconclusive'])
        body=obj({key:{'type':'string','enum':values},'reason':{'type':'string'},'evidence':{'type':'array','items':reference}})
    return {'type':'json_schema','json_schema':{'name':kind+'_'+style,'strict':True,'schema':body}}

