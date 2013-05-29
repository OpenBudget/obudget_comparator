#encoding: utf8

import json
import itertools
import Levenshtein
import re

INFLATION = {1992: 2.338071159424868,
 1993: 2.1016785142253185,
 1994: 1.8362890269054741,
 1995: 1.698638328862775,
 1996: 1.5360153664058611,
 1997: 1.4356877762122495,
 1998: 1.3217305991625745,
 1999: 1.3042057718241757,
 2000: 1.3042057718241757,
 2001: 1.2860800081392196,
 2002: 1.2076314957018655,
 2003: 1.2308469660644752,
 2004: 1.2161648953888384,
 2005: 1.1878270593983091,
 2006: 1.1889814138002117,
 2007: 1.1499242230869946,
 2008: 1.1077747422214268,
 2009: 1.0660427753379829,
 2010: 1.0384046275616676,
 2011: 1.0163461588107117,
 2012: 1.0,
 2013: 1.0,
 2014: 1.0,
}

strings = []
strings_rev = {}
no_ws = re.compile('[ ]+')

def get_string_id(s):
    s=s.strip()
    s=no_ws.sub(' ',s)
    if s in strings_rev.keys():
        return strings_rev[s]
    ret = len(strings)
    strings_rev[s] = ret
    strings.append(s)
    return ret

def budget_file():
    for line in file('master.json'):
        if line.strip():
            data = json.loads(line)
            z = dict([ (k,v) for k,v in data.iteritems() if v is not None ])
            yield z

def copy_node_no_children(node):
    return { 'code': node['code'],
             'title': node['title'],
             'value': node['value'],
             'group': node.get('group',""),
             'parent_value': node.get('parent_value',1),
             'children': {} }

def filter_tree(node,func):
    orig_node = copy_node_no_children(node)
    new_node = copy_node_no_children(node)
    for step, child in node.get('children',{}).iteritems():
        new_child = filter_tree(child,func)
        if new_child:
            new_node['children'][step] = new_child 
    if not func(new_node): 
        return orig_node
    return new_node

def merge_trees(root1, root2):
    new_node = copy_node_no_children(root1)
    new_node['value'] = [ new_node['value'] ]
    new_node['value'].append(root2['value'])
    new_node['parent_value'] = root2['parent_value']

    roots = [ root1, root2 ]
    codesets = [ set(root['children'].keys()) for root in roots ]
    shared_codes = codesets[0].intersection(codesets[1])
    other_codes = [ codeset - shared_codes for codeset in codesets ]
    group = ""
    parent_value = 1
    for code in shared_codes:
        child_nodes = [ root['children'][code] for root in roots ]
        titles = [ node['title'] for node in child_nodes ]
        lratio = Levenshtein.ratio(*titles)
        if lratio < 0.5:
            for codes in other_codes: codes.add(code)
            continue
        new_node['children'][code] = merge_trees(*child_nodes)
        group = child_nodes[1]['group']
        parent_value = child_nodes[1]['parent_value']

    if sum([len(x) for x in other_codes]) > 0:
        others_node = { 'code' : root1['code']+'**',
                        'title' : u'סעיפים שונים',
                        'value' : [0,0] }
        for i in range(2):
            for code in other_codes[i]:
                others_node['value'][i] += roots[i]['children'][code]['value']
    
        new_node['children']['**'] = others_node

    return new_node

def build_tree( data, year, field, income=False ):
    def item_filter(item):
        return (int(item.get('year',0))==year and 
                int(item.get(field,-1))>=0 and 
                income == item.get('code','').startswith('0000') and
                item.get('title','') != '')
    filtered_items = ( item for item in data if item_filter(item) )
    filtered_items = [ { 'code':item['code'][2 if income else 0:], 
                         'title':item['title'], 
                         'value':item[field]*INFLATION[year] } 
                       for item in filtered_items ]
    filtered_items.sort( key=lambda item: item['code'] )

    if len(filtered_items) == 0: return {}
    root = filtered_items[0]
    assert(root['code']== "00")

    for item in filtered_items[1:]:
        node = root
        code = item['code'][2:]
        group = None
        parent_value = node['value']
        try:
            while len(code)>2:
                step = code[:2]
                node = node['children'][step]
                code = code[2:]
                group = "%s (%s)" % (node['title'], node['code'])
                parent_value = node['value']
        except KeyError:
            continue
        item['group'] = group if group else "%s (%s)" % (item['title'], item['code'])
        item['parent_value'] = parent_value
        node.setdefault('children',{})[code] = item

    root = filter_tree(root, lambda node: len(node.get('children',{}))>1 )

    return root

def extract_by_depth(node,target_depth,depth=0):
    if depth==target_depth: 
        yield copy_node_no_children(node)
        return
    if len(node.get('children',{})) == 0: 
        yield copy_node_no_children(node)
        return
    keys = node.get('children').keys()
    keys.sort()
    for key in keys:
        child = node.get('children')[key]
        for x in extract_by_depth(child,target_depth,depth+1): yield x

def key_for_diff(year1,field1,year2,field2,income,divein=None):
    key = "%s.%s/%s.%s/%s%s" % ( year1, field1, year2, field2, "income" if income else "spending", "" if not divein else "/%s" % divein )
    print key
    return key

def adapt_for_js(items):
    for item in items:
        if item['value'] != [0,0]:
            yield { 'budget_0'  : item['value'][0],
                    'budget_1'  : item['value'][1],
                    'name'      : get_string_id(item['title']),
                    'p'         : get_string_id(item['group']),
                    'pv'        : item['parent_value'],
                    'id'        : item['code'],
                    'change'    : 100*item['value'][1] / item['value'][0] - 100 if item['value'][0] > 0 else 99999
                }

def get_items_for(year1,field1,year2,field2,income):
    tree1 = build_tree(budget_file(), year1, field1, income)
    tree2 = build_tree(budget_file(), year2, field2, income)
    merged = merge_trees(tree1, tree2)

    merged = filter_tree(merged, lambda node: node['value'][0] > 0)
    merged = filter_tree(merged, lambda node: sum([ (node['value'][i] > 0) and
                                                    1.0 * node.get('children',{}).get('**',{'value':[0,0]})['value'][i] / node['value'][i] < 0.5 
                                                    for i in range(2)]
                                              ) == 2)
    merged = filter_tree(merged, lambda node: len(node.get('children',{}))>1 )
     
    yield key_for_diff(year1,field1,year2,field2,income), list(adapt_for_js(extract_by_depth(merged,2)))

    for part in merged['children'].keys():
        yield key_for_diff(year1,field1,year2,field2,income,merged['code']+part), list(adapt_for_js(extract_by_depth(merged['children'][part],2)))

if __name__=="__main__":
    generated_diffs = [ (2011, "net_allocated", 2011, "net_used", False),
                        (2012, "net_allocated", 2012, "net_used", False),
                        (2011, "net_allocated", 2011, "net_used", True),
                        (2012, "net_allocated", 2012, "net_used", True),
                        (2011, "net_used",      2012, "net_used", False),
                        (2011, "net_used",      2012, "net_used", True),
                        (2011, "net_allocated", 2012, "net_allocated", False),
                        (2012, "net_allocated", 2013, "net_allocated", False),
                        (2012, "net_allocated", 2014, "net_allocated", False),
                        (2013, "net_allocated", 2014, "net_allocated", False), ]
                        # (2011, "net_allocated", 2012, "net_allocated", True),
                        # (2012, "net_allocated", 2013, "net_allocated", True),
                        # (2012, "net_allocated", 2014, "net_allocated", True),
                        #(2013, "net_allocated", 2014, "net_allocated", True), ]
    diffs = itertools.chain( *( get_items_for(*diff) for diff in generated_diffs ) )
    diffs = dict(list(diffs))
    out = file('data.js','w')
    out.write('budget_array_data = %s;\n' % json.dumps(diffs))
    out.write('strings = %s;\n' % json.dumps(strings))
    #print json.dumps(dict(diffs))
    
    