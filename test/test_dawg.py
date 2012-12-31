import sys

# Needed to pass
# http://www.w3.org/2009/sparql/docs/tests/data-sparql11/
# syntax-update-2/manifest#syntax-update-other-01
sys.setrecursionlimit(6000)  # default is 1000


import collections
import datetime
import isodate
from StringIO import StringIO

from rdflib import (
    ConjunctiveGraph, Graph, Namespace, RDF, RDFS, URIRef, BNode, Literal)
from rdflib.query import Result
from rdflib.compare import isomorphic

import rdflib_sparql as rdflib_sparql_module
from rdflib_sparql.algebra import (
    pprintAlgebra, translateQuery, translateUpdate)
from rdflib_sparql.parser import parseQuery, parseUpdate
from rdflib_sparql.results.rdfresults import RDFResultParser
from rdflib_sparql.update import evalUpdate

from nose.tools import nottest, eq_ as eq
from nose import SkipTest

from urlparse import urljoin

# do not resolve URIs looking for more data


DEBUG_FAIL = True
DEBUG_FAIL = False

DEBUG_ERROR = True
DEBUG_ERROR = False

SPARQL10Tests = True
SPARQL10Tests = False

SPARQL11Tests = True
#SPARQL11Tests=False

DETAILEDASSERT = True
#DETAILEDASSERT=False

MF = Namespace('http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#')
QT = Namespace('http://www.w3.org/2001/sw/DataAccess/tests/test-query#')
UP = Namespace('http://www.w3.org/2009/sparql/tests/test-update#')

DAWG = Namespace('http://www.w3.org/2001/sw/DataAccess/tests/test-dawg#')
DOAP = Namespace('http://usefulinc.com/ns/doap#')
FOAF = Namespace('http://xmlns.com/foaf/0.1/')
EARL = Namespace("http://www.w3.org/ns/earl#")

NAME = None

fails = collections.Counter()
errors = collections.Counter()

failed_tests = []
error_tests = []

EARL_REPORT = Graph()


rdflib_sparql = URIRef('https://github.com/gromgull/rdflib-sparql')

EARL_REPORT.add((rdflib_sparql, DOAP.homepage, rdflib_sparql))
EARL_REPORT.add((rdflib_sparql, DOAP.name, Literal("rdflib_sparql")))
EARL_REPORT.add((rdflib_sparql, RDF.type, DOAP.Project))

me = URIRef('http://gromgull.net/me')
EARL_REPORT.add((me, RDF.type, FOAF.Person))
EARL_REPORT.add((me, FOAF.homepage, URIRef("http://gromgull.net")))
EARL_REPORT.add((me, FOAF.name, Literal("Gunnar Aastrand Grimnes")))

try:
    skiptests = dict([(URIRef(x.strip().split(
        "\t")[0]), x.strip().split("\t")[1]) for x in file("skiptests.list")])
except IOError:
    skiptests = set()


def _fmt(f):
    if f.endswith(".rdf"):
        return "xml"
    return "turtle"


def bindingsCompatible(a, b):

    """

    Are two binding-sets compatible.

    From the spec: http://www.w3.org/2009/sparql/docs/tests/#queryevaltests

    A SPARQL implementation passes a query evaluation test if the
    graph produced by evaluating the query against the RDF dataset
    (and encoding in the DAWG result set vocabulary, if necessary) is
    equivalent [RDF-CONCEPTS] to the graph named in the result (after
    encoding in the DAWG result set vocabulary, if necessary). Note
    that, solution order only is considered relevant, if the result is
    expressed in the test suite in the DAWG result set vocabulary,
    with explicit rs:index triples; otherwise solution order is
    considered irrelevant for passing. Equivalence can be tested by
    checking that the graphs are isomorphic and have identical IRI and
    literal nodes. Note that testing whether two result sets are
    isomorphic is simpler than full graph isomorphism. Iterating over
    rows in one set, finding a match with the other set, removing this
    pair, then making sure all rows are accounted for, achieves the
    same effect.
    """

    def rowCompatible(x, y):
        m = {}
        y = dict(y)
        for v1, b1 in x:
            if v1 not in y:
                return False
            if isinstance(b1, BNode):
                if b1 in m:
                    if y[v1] != m[b1]:
                        return False
                else:
                    m[b1] = y[v1]
            else:
                if y[v1] != b1:
                    return False
        return True

    if not a:
        if b:
            return False
        return True

    x = iter(a).next()

    for y in b:
        if rowCompatible(x, y):
            if bindingsCompatible(a - set((x,)), b - set((y,))):
                return True

    return False


def pp_binding(solutions):
    """
    Pretty print a single binding - for less eye-strain when debugging
    """
    return "\n[" + ",\n\t".join("{" + ", ".join("%s:%s" % (
                x[0], x[1].n3()) for x in bindings.items()) + "}"
                                    for bindings in solutions) + "]\n"


@nottest
def update_test(t):

    # the update-eval tests refer to graphs on http://example.org
    rdflib_sparql_module.SPARQL_LOAD_GRAPHS = False

    uri, name, comment, data, graphdata, query, res, syntax = t

    try:
        g = ConjunctiveGraph()

        if not res:
            if syntax:
                translateUpdate(parseUpdate(file(query[7:])))
            else:
                try:
                    translateUpdate(parseUpdate(file(query[7:])))
                    raise AssertionError("Query shouldn't have parsed!")
                except:
                    pass  # negative syntax test
            return

        resdata, resgraphdata = res

        # read input graphs
        if data:
            g.default_context.load(data, format=_fmt(data))

        if graphdata:
            for x, l in graphdata:
                g.load(x, publicID=URIRef(l), format=_fmt(x))

        req = translateUpdate(parseUpdate(file(query[7:])))
        evalUpdate(g, req)

        # read expected results
        resg = ConjunctiveGraph()
        if resdata:
            resg.default_context.load(resdata, format=_fmt(resdata))

        if resgraphdata:
            for x, l in resgraphdata:
                resg.load(x, publicID=URIRef(l), format=_fmt(x))

        eq(set(x.identifier for x in g.contexts() if x != g.default_context),
           set(x.identifier for x in resg.contexts()
                            if x != resg.default_context))
        assert isomorphic(g.default_context, resg.default_context), \
                        'Default graphs are not isomorphic'

        for x in g.contexts():
            if x == g.default_context:
                continue
            assert isomorphic(x, resg.get_context(x.identifier)), \
                "Graphs with ID %s are not isomorphic" % x.identifier

    except Exception, e:

        if isinstance(e, AssertionError):
            failed_tests.append(uri)
            fails[e.message] += 1
        else:
            error_tests.append(uri)
            errors[str(e)] += 1

        if DEBUG_ERROR and not isinstance(e, AssertionError) or DEBUG_FAIL:
            print "======================================"
            print uri
            print name
            print comment

            if not res:
                if syntax:
                    print "Positive syntax test"
                else:
                    print "Negative syntax test"

            if data:
                print "----------------- DATA --------------------"
                print ">>>", data
                print file(data[7:]).read()
            if graphdata:
                print "----------------- GRAPHDATA --------------------"
                for x, l in graphdata:
                    print ">>>", x, l
                    print file(x[7:]).read()

            print "----------------- Request -------------------"
            print ">>>", query
            print file(query[7:]).read()

            if res:
                if resdata:
                    print "----------------- RES DATA --------------------"
                    print ">>>", resdata
                    print file(resdata[7:]).read()
                if resgraphdata:
                    print "----------------- RES GRAPHDATA -------------------"
                    for x, l in resgraphdata:
                        print ">>>", x, l
                        print file(x[7:]).read()

            print "------------- MY RESULT ----------"
            print g.serialize(format='trig')

            try:
                pq = translateUpdate(parseUpdate(file(query[7:]).read()))
                print "----------------- Parsed ------------------"
                #pprintAlgebra(pq)
                print pq
            except:
                print "(parser error)"

            print e.message.decode('string-escape')

            import pdb
            pdb.post_mortem()
        raise


@nottest  # gets called by generator
def query_test(t):
    uri, name, comment, data, graphdata, query, resfile, syntax = t

    # the query-eval tests refer to graphs to load by resolvable filenames
    rdflib_sparql_module.SPARQL_LOAD_GRAPHS = True

    if uri in skiptests:
        raise SkipTest()

    def skip(reason='(none)'):
        print "Skipping %s from now on." % uri
        f = file("skiptests.list", "a")
        f.write("%s\t%s\n" % (uri, reason))
        f.close()

    try:
        g = ConjunctiveGraph()
        if data:
            g.default_context.load(data, format=_fmt(data))

        if graphdata:
            for x in graphdata:
                g.load(x, format=_fmt(x))

        if not resfile:
            # no result - syntax test

            if syntax:
                translateQuery(parseQuery(
                    file(query[7:]).read()), base=urljoin(query, '.'))
            else:
                # negative syntax test
                try:
                    translateQuery(parseQuery(
                        file(query[7:]).read()), base=urljoin(query, '.'))

                    assert False, 'Query should not have parsed!'
                except:
                    pass  # it's fine - the query should not parse
            return

        # eval test - carry out query
        res2 = g.query(file(query[7:]).read(), base=urljoin(query, '.'))

        if resfile.endswith('ttl'):
            resg = Graph()
            resg.load(resfile, format='turtle', publicID=resfile)
            res = RDFResultParser().parse(resg)
        elif resfile.endswith('rdf'):
            resg = Graph()
            resg.load(resfile, publicID=resfile)
            res = RDFResultParser().parse(resg)
        elif resfile.endswith('srj'):
            res = Result.parse(file(resfile[7:]), format='json')
        elif resfile.endswith('tsv'):
            res = Result.parse(file(resfile[7:]), format='tsv')

        elif resfile.endswith('csv'):
            res = Result.parse(file(resfile[7:]), format='csv')

            # CSV is lossy, round-trip our own resultset to
            # lose the same info :)
            s = StringIO()
            res2.serialize(s, format='csv')
            s = StringIO(s.getvalue())  # hmm ?
            res2 = Result.parse(s, format='csv')

        else:
            res = Result.parse(file(resfile[7:]), format='xml')

        if not DETAILEDASSERT:
            eq(res.type, res2.type, 'Types do not match')
            if res.type == 'SELECT':
                eq(set(res.vars), set(res2.vars), 'Vars do not match')
                assert bindingsCompatible(
                            set(frozenset(x.iteritems())
                                for x in res.bindings),
                            set(frozenset(x.iteritems())
                                for x in res2.bindings)
                            ), 'Bindings do not match'
            elif res.type == 'ASK':
                eq(res.askAnswer, res2.askAnswer, 'Ask answer does not match')
            elif res.type in ('DESCRIBE', 'CONSTRUCT'):
                assert isomorphic(
                    res.graph, res2.graph), 'graphs are not isomorphic!'
            else:
                raise Exception('Unknown result type: %s' % res.type)
        else:

            eq(res.type, res2.type,
               'Types do not match: %r != %r' % (res.type, res2.type))
            if res.type == 'SELECT':
                eq(set(res.vars),
                   set(res2.vars), 'Vars do not match: %r != %r' % (
                                        set(res.vars), set(res2.vars)))
                assert bindingsCompatible(
                        set(frozenset(x.iteritems())
                                for x in res.bindings),
                        set(frozenset(x.iteritems())
                                for x in res2.bindings)
                        ), 'Bindings do not match: %r != %r' % (
                        pp_binding(res.bindings),
                        pp_binding(res2.bindings))
            elif res.type == 'ASK':
                eq(res.askAnswer,
                   res2.askAnswer, "Ask answer does not match: %r != %r" % (
                                            res.askAnswer, res2.askAnswer))
            elif res.type in ('DESCRIBE', 'CONSTRUCT'):
                assert isomorphic(
                    res.graph, res2.graph), 'graphs are no isomorphic!'
            else:
                raise Exception('Unknown result type: %s' % res.type)

    except Exception, e:

        if isinstance(e, AssertionError):
            failed_tests.append(uri)
            fails[e.message] += 1
        else:
            error_tests.append(uri)
            errors[str(e)] += 1

        if DEBUG_ERROR and not isinstance(e, AssertionError) or DEBUG_FAIL:
            print "======================================"
            print uri
            print name
            print comment

            if not resfile:
                if syntax:
                    print "Positive syntax test"
                else:
                    print "Negative syntax test"

            if data:
                print "----------------- DATA --------------------"
                print ">>>", data
                print file(data[7:]).read()
            if graphdata:
                print "----------------- GRAPHDATA --------------------"
                for x in graphdata:
                    print ">>>", x
                    print file(x[7:]).read()

            print "----------------- Query -------------------"
            print ">>>", query
            print file(query[7:]).read()
            if resfile:
                print "----------------- Res -------------------"
                print ">>>", resfile
                print file(resfile[7:]).read()

            try:
                pq = parseQuery(file(query[7:]).read())
                print "----------------- Parsed ------------------"
                pprintAlgebra(translateQuery(pq, base=urljoin(query, '.')))
            except:
                print "(parser error)"

            #import traceback
            #traceback.print_exc()
            print e.message.decode('string-escape')

            import pdb
            pdb.post_mortem()
            #pdb.set_trace()
            #nose.tools.set_trace()
        raise


def read_manifest(f):

    def _str(x):
        if x is not None:
            return str(x)
        return None

    g = Graph()
    g.load(f, format='turtle')

    for m in g.subjects(RDF.type, MF.Manifest):

        for col in g.objects(m, MF.include):
            for i in g.items(col):
                for x in read_manifest(i):
                    yield x

        for col in g.objects(m, MF.entries):
            for e in g.items(col):

                if not ((e, DAWG.approval, DAWG.Approved) in g or
                        (e, DAWG.approval, DAWG.NotClassified) in g):
                                continue

                t = g.value(e, RDF.type)

                tester = query_test

                if t in (MF.ServiceDescriptionTest, MF.ProtocolTest):
                    continue  # skip tests we do not know

                name = g.value(e, MF.name)
                comment = g.value(e, RDFS.comment)

                if t in (MF.QueryEvaluationTest, MF.CSVResultFormatTest):
                    a = g.value(e, MF.action)
                    query = g.value(a, QT.query)
                    data = g.value(a, QT.data)
                    graphdata = list(g.objects(a, QT.graphData))
                    res = g.value(e, MF.result)
                    syntax = True
                elif t in (MF.UpdateEvaluationTest, UP.UpdateEvaluationTest):
                    a = g.value(e, MF.action)
                    query = g.value(a, UP.request)
                    data = g.value(a, UP.data)
                    graphdata = []
                    for gd in g.objects(a, UP.graphData):
                        graphdata.append((g.value(gd, UP.graph),
                                          g.value(gd, RDFS.label)))

                    r = g.value(e, MF.result)
                    resdata = g.value(r, UP.data)
                    resgraphdata = []
                    for gd in g.objects(r, UP.graphData):
                        resgraphdata.append((g.value(gd, UP.graph),
                                             g.value(gd, RDFS.label)))

                    res = resdata, resgraphdata
                    syntax = True
                    tester = update_test

                elif t in (MF.NegativeSyntaxTest11, MF.PositiveSyntaxTest11):
                    query = g.value(e, MF.action)
                    if t == MF.NegativeSyntaxTest11:
                        syntax = False
                    else:
                        syntax = True
                    data = None
                    graphdata = None
                    res = None

                elif t in (MF.PositiveUpdateSyntaxTest11,
                           MF.NegativeUpdateSyntaxTest11):
                    query = g.value(e, MF.action)
                    if t == MF.NegativeUpdateSyntaxTest11:
                        syntax = False
                    else:
                        syntax = True
                    data = None
                    graphdata = None
                    res = None
                    tester = update_test

                else:
                    print "I dont know DAWG Test Type %s" % t
                    continue

                yield tester, (e, _str(name), _str(comment),
                               _str(data), graphdata, _str(query),
                               res, syntax)


def test_dawg():

    if SPARQL10Tests:
        for t in read_manifest("test/DAWG/data-r2/manifest-evaluation.ttl"):
            yield t

    if SPARQL11Tests:
        for t in read_manifest("test/DAWG/data-sparql11/manifest-all.ttl"):
            yield t


def earl(test, res, info=None):
    a = BNode()
    EARL_REPORT.add((a, RDF.type, EARL.Assertion))
    EARL_REPORT.add((a, EARL.assertedBy, me))
    EARL_REPORT.add((a, EARL.test, test))
    EARL_REPORT.add((a, EARL.subject, rdflib_sparql))

    r = BNode()
    EARL_REPORT.add((a, EARL.result, r))
    EARL_REPORT.add((r, RDF.type, EARL.TestResult))

    EARL_REPORT.add((r, EARL.outcome, EARL[res]))
    if info:
        EARL_REPORT.add((r, EARL.info, Literal(info)))


if __name__ == '__main__':

    import sys
    import time
    start = time.time()
    if len(sys.argv) > 1:
        NAME = sys.argv[1]
        DEBUG_FAIL = True
    i = 0
    success = 0

    skip = 0
    for f, t in test_dawg():
        if NAME and not str(t[0]).startswith(NAME):
            continue
        i += 1
        try:
            f(t)
            earl(t[0], "passed")
            success += 1

        except SkipTest:
            earl(t[0], "untested", skiptests[t[0]])
            print "skipping %s - %s" % (t[0], skiptests[t[0]])
            skip += 1

        except KeyboardInterrupt:
            raise
        except AssertionError:
            earl(t[0], "failed")
        except:
            earl(t[0], "failed", "error")
            import traceback
            traceback.print_exc()
            sys.stderr.write("%s\n" % t[0])

    print "\n----------------------------------------------------\n"
    print "Failed tests:"
    for f in failed_tests:
        print f

    print "\n----------------------------------------------------\n"
    print "Error tests:"
    for f in error_tests:
        print f

    print "\n----------------------------------------------------\n"

    print "Most common fails:"
    for e in fails.most_common(10):
        e = str(e)
        print e[:450] + (e[450:] and "...")

    print "\n----------------------------------------------------\n"

    if errors:

        print "Most common errors:"
        for e in errors.most_common(10):
            print e
    else:
        print "(no errors!)"

    f = sum(fails.values())
    e = sum(errors.values())

    if success + f + e + skip != i:
        print "(Something is wrong, %d!=%d)" % (success + f + e + skip, i)

    print "\n%d tests, %d passed, %d failed, %d errors, \
          %d skipped (%.2f%% success)" % (
                    i, success, f, e, skip, 100. * success / i)
    print "Took %.2fs" % (time.time() - start)

    if not NAME:

        now = isodate.datetime_isoformat(datetime.datetime.utcnow())

        tf = file("testruns.txt", "a")
        tf.write("%s\n%d tests, %d passed, %d failed, %d errors, \
                 %d skipped (%.2f%% success)\n\n" % (
                    now, i, success, f, e, skip, 100. * success / i))
        tf.close()

        earl_report = 'test_reports/earl_%s.ttl' % now

        EARL_REPORT.serialize(earl_report, format='n3')
        EARL_REPORT.serialize('test_reports/earl_latest.ttl', format='n3')
        print "Wrote EARL-report to '%s'" % earl_report
