import sys
sys.path.append(".")
import translationunitcache
import os
import os.path
import pickle
import sys
import gzip
import re
import platform
import Queue
import time
from parsehelp import parsehelp


scriptpath = os.path.dirname(os.path.abspath(__file__))
opts = ["-I%s/../clang/include" % scriptpath]

golden = {}
testsAdded = False
tu = None
currfile = None

GOLDFILE = "unittests/gold.txt.gz"
debug = False
onlywarn = False
update = False
debugnew = False
dryrun = False
disableplatformspecific = False
goto_def = True
goto_imp = True
complete = True

for arg in sys.argv[1:]:
    if arg == "-nogotodef":
        goto_def = False
    elif arg == "-nogotoimp":
        goto_imp = False
    elif arg == "-nocomplete":
        complete = False
    elif arg == "-debug":
        debug = True
    elif arg == "-warn":
        onlywarn = True
    elif arg == "-update":
        update = True
    elif arg == "-debugnew":
        debugnew = True
    elif arg == "-dryrun":
        dryrun = True
    elif arg == "-disableplatformspecific":
        disableplatformspecific = True
    else:
        raise Exception("Bad argument")


filter = re.compile("(^_.*\tmacro$)|(^__)|(OBJC_NEW_PROPERTIES)|(type_info)|(i386)|linux|unix")

if os.access(GOLDFILE, os.R_OK):
    f = gzip.GzipFile(GOLDFILE, 'rb')
    golden = pickle.load(f)
    for key in golden:
        if golden[key] and not isinstance(golden[key], str):
            new = []
            for name in golden[key]:
                if not filter.match(name[0]):
                    new.append(name)
            golden[key] = new
    f.close()


def fail(message, forcewarn=False):
    if onlywarn or forcewarn:
        print message
    else:
        raise Exception(message)

def add_test_ex(key, test, platformspecific=False, noneok=False):
    global off
    global testsAdded

    dn = key not in golden and debugnew

    output = None
    if dn or not debugnew:
        output = test()
    if output and not isinstance(output, str):
        new = []
        for name in output:
            if not filter.match(name[0]):
                new.append(name)
        output = new

    if debug or dn:
        print key
        if output == None:
            print "\tNone"
        elif isinstance(output, str):
            print "\t%s" % output
        elif len(output) == 0:
            print "\t[]"
        else:
            for data in output:
                print "\t%s" % str(data)
    if debugnew:
        return
    if not key in golden:
        golden[key] = output
        testsAdded = True
    else:
        gold = golden[key]
        if update:
            golden[key] = output
        if not (platformspecific and noneok) and ((gold == None and output != None) or (output == None and gold != None)):
            fail("Test failed: %s - %s" % (key, "gold was None, output wasn't %s" % str(output) if gold == None else "output was None, but gold wasn't %s" % str(gold)))
        if platformspecific and disableplatformspecific:
            return
        if gold != None and output != None:
            if type(gold) != type(output):
                fail("gold and output type differs: %s %s" % (type(gold), type(output)))
            elif isinstance(gold, str):
                if gold != output:
                    fail("gold and output differs: %s %s" % (gold, output))
            else:
                gold = [str(x) for x in gold]
                output = [str(x) for x in output]
                goldset = set(gold)
                outputset = set(output)
                ingold = goldset - outputset
                inoutput = outputset - goldset
                for i in ingold:
                    fail("Test failed: %s - Was in gold but not output: %s" % (key, i))
                for i in inoutput:
                    fail("Test failed: %s - Was in output but not gold: %s" % (key, i))

goto_def_test_count = 0

def defimp_base(queue):
    allowed_sleeps = 50

    while queue.empty():
        time.sleep(0.1)
        if allowed_sleeps == 0:
            raise Exception("goto def timed out")
        allowed_sleeps -= 1

    res = queue.get()
    if isinstance(res, list):
        nl = []
        for a,b in res:
            name, linecol = b.split(":", 1)
            name = os.path.relpath(name)
            nl.append((a, "%s:%s" % (name, linecol)))
        res = nl
    elif res != None:
        name, linecol = res.split(":", 1)
        name = os.path.relpath(name)
        res =  "%s:%s" % (name, linecol)
    return res


def add_goto_def_test(data, offset):
    global goto_def_test_count
    goto_def_test_count += 1
    key = "goto-def-%d" % (goto_def_test_count)
    queue = Queue.Queue()
    def get_res(queue, data, offset):
        tu.get_definition(data, offset, lambda a: queue.put(a), ["."])
        return defimp_base(queue)
    add_test_ex(key, lambda: get_res(queue, data, offset))

goto_imp_test_count = 0
def add_goto_imp_test(data, offset):
    global goto_imp_test_count
    goto_imp_test_count += 1
    key = "goto-imp-%d" % (goto_imp_test_count)
    queue = Queue.Queue()
    def get_res(queue, data, offset):
        tu.get_implementation(data, offset, lambda a: queue.put(a), ["."])
        return defimp_base(queue)
    add_test_ex(key, lambda: get_res(queue, data, offset))


def add_completion_test(currtest, platformspecific=False, noneok=False):
    key = "%s-%s" % (currfile, currtest)
    add_test_ex(key, lambda: tu.cache.complete(currtest, ""), platformspecific, noneok)


def get_tu(filename):
    global currfile
    currfile = filename
    myopts = []
    myopts.extend(opts)
    if not filename.endswith(".mm"):
        myopts.append("-x")
        myopts.append("c++")
    else:
        myopts.append("-ObjC")
    return translationunitcache.tuCache.get_translation_unit(filename, myopts)

def read_file(filename):
    f = open(filename)
    data = f.read()
    f.close()
    return data

if goto_def:
    tu = get_tu("src/main.cpp")
    data = read_file("src/main.cpp")

    data2 = """/*

            Just to make the translation unit no longer map 1:1

            */
            """ + data
    add_goto_def_test(data, data.rfind("cache")+2)
    add_goto_def_test(data, data.rfind("Cache")+2)
    add_goto_def_test(data, data.rfind("CXCursor")+2)
    add_goto_def_test(data, data.rfind(">complete")+3)
    add_goto_def_test(data, data.rfind(">findType")+3)
    add_goto_def_test(data, data.rfind("disp", 0, data.rfind("disp"))+3)
    add_goto_def_test(data, data.rfind("EntryList")+2)
    add_goto_def_test(data, data.rfind("clang_")+2)
    add_goto_def_test(data, data.rfind("NumResults")+2)
    add_goto_def_test(data, data.rfind(" res-")+2)
    add_goto_def_test(data, data.rfind("CXCursor_FunctionTemplate")+2)
    add_goto_def_test(data, data.find("mNamespaces")+2)
    add_goto_def_test(data, data.find("mFound")+2)
    add_goto_def_test(data2, data2.rfind("cache")+2)
    add_goto_def_test(data2, data2.rfind("Cache")+2)
    add_goto_def_test(data2, data2.rfind("CXCursor")+2)
    add_goto_def_test(data2, data2.rfind(">complete")+3)
    add_goto_def_test(data2, data2.rfind(">findType")+3)
    add_goto_def_test(data2, data2.rfind("disp", 0, data2.rfind("disp"))+3)
    add_goto_def_test(data2, data2.rfind("EntryList")+2)
    add_goto_def_test(data2, data2.rfind("clang_")+2)
    add_goto_def_test(data2, data2.rfind("NumResults")+2)
    add_goto_def_test(data2, data2.rfind(" res-")+2)
    add_goto_def_test(data2, data2.rfind("CXCursor_FunctionTemplate")+2)
    add_goto_def_test(data2, data2.find("mNamespaces")+2)
    add_goto_def_test(data2, data2.find("mFound")+2)




if goto_imp:
    tu = get_tu("src/main.cpp")
    data = read_file("src/main.cpp")
    data2 = """/*

            Just to make the translation unit no longer map 1:1

            */""" + data
    add_goto_imp_test(data, data.rfind("cache")+2)
    add_goto_imp_test(data, data.rfind("Cache")+2)
    add_goto_imp_test(data, data.rfind("CXCursor")+2)
    add_goto_imp_test(data, data.rfind(">complete")+3)
    add_goto_imp_test(data, data.rfind(">findType")+3)
    add_goto_imp_test(data, data[:data.rfind("disp")].rfind("disp")+3)
    add_goto_imp_test(data, data.rfind("EntryList")+2)
    add_goto_imp_test(data, data.rfind("clang_")+2)
    add_goto_imp_test(data, data.rfind("NumResults")+2)
    add_goto_imp_test(data, data.rfind(" res-")+2)
    add_goto_imp_test(data, data.rfind("CXCursor_FunctionTemplate")+2)
    add_goto_imp_test(data, data.find("mNamespaces")+2)
    add_goto_imp_test(data, data.find("mFound")+2)
    add_goto_imp_test(data2, data2.rfind("cache")+2)
    add_goto_imp_test(data2, data2.rfind("Cache")+2)
    add_goto_imp_test(data2, data2.rfind("CXCursor")+2)
    add_goto_imp_test(data2, data2.rfind(">complete")+3)
    add_goto_imp_test(data2, data2.rfind(">findType")+3)
    add_goto_imp_test(data2, data2[:data2.rfind("disp")].rfind("disp")+3)
    add_goto_imp_test(data2, data2.rfind("EntryList")+2)
    add_goto_imp_test(data2, data2.rfind("clang_")+2)
    add_goto_imp_test(data2, data2.rfind("NumResults")+2)
    add_goto_imp_test(data2, data2.rfind(" res-")+2)
    add_goto_imp_test(data2, data2.rfind("CXCursor_FunctionTemplate")+2)
    add_goto_imp_test(data2, data2.find("mNamespaces")+2)
    add_goto_imp_test(data2, data2.find("mFound")+2)
    add_goto_imp_test(data2, data2.find("strcmp")+2)
    add_goto_imp_test(data2, data2.find("strlen")+2)
    tu2 = get_tu("./unittests/search2.cpp")
    add_goto_imp_test(data2, data2.find("strncmp")+2)

    # index 1 would be "don't redo search/don't do search" so if we get a
    # timeout exception we know the test failed
    old = translationunitcache.display_user_selection
    translationunitcache.display_user_selection = lambda a, b: b(1)
    add_goto_imp_test(data2, data2.find("strncmp")+2)

    # And in this instance, we want to select one of the options previously found
    def check_correct(a, b):
        assert len(a) == 5
        b(2)
    translationunitcache.display_user_selection = check_correct
    add_goto_imp_test(data2, data2.find("strcmp")+2)

    translationunitcache.display_user_selection = old
    translationunitcache.searchcache.clear()
    tu2.var.reparse()
    add_goto_imp_test(data2, data2.find("strncmp")+2)

    tu = get_tu("unittests/search3.h")
    data = read_file("unittests/search3.h")
    add_goto_imp_test(data, data.find("hello")+2)
    add_goto_imp_test(data, data.find("notfound")+2)
    add_goto_imp_test(data, data.find("elsewhere")+2)


if complete:
    # ---------------------------------------------------------

    tu = get_tu("unittests/1.cpp")
    add_completion_test("", True)
    add_completion_test("new ", True)

    # ---------------------------------------------------------

    tu = get_tu("unittests/2.cpp")
    add_completion_test("Class1 c;\nc.")
    add_completion_test("void Class1::publicFunction() {", True)
    add_completion_test("void Class2::something() {", True)
    add_completion_test("Class1::")
    add_completion_test("void Class2::something() { Class1::")
    add_completion_test("void Class2::something() { Class2::")
    add_completion_test("Class3 c3; c3.")
    add_completion_test("void Class2::something() { Class3::")
    add_completion_test("void Class2::something() { Class3 c3; c3.")
    add_completion_test("void Class2::something() { this->")
    add_completion_test("void Class1::something() { this->")
    add_completion_test("Test t[1]; t.")
    add_completion_test("Test t[1]; t[0].")
    add_completion_test("new ")
    add_completion_test("new Cla")

    data = read_file("unittests/2.cpp")
    add_completion_test(data + "Test t[1]; t.")
    add_completion_test(data + "Test t[1]; t[0].")
    add_completion_test(data + "t2.")
    add_completion_test(data + "t2[0].")


    # ---------------------------------------------------------

    tu = get_tu("unittests/3.cpp")
    add_completion_test("new ", True)
    add_completion_test("new std::", True)
    add_completion_test("new std::rel_ops::", True)
    add_completion_test("new std2::")
    add_completion_test("new blah::", True)
    add_completion_test("new Test::")
    add_completion_test("std::", True)
    add_completion_test("std2::")
    add_completion_test("Test::")
    add_completion_test("std::string::", True, True)
    add_completion_test("std::vector<int>::", True)
    add_completion_test("Test::Class1::")
    add_completion_test("Test::intvector::", True)
    add_completion_test("Test::intvector s; s.", True)
    add_completion_test("Test::intvector s; s[0].", True)
    add_completion_test("Test::stringvector::")
    add_completion_test("Test::stringvector s; s.")
    add_completion_test("Test::stringvector s; s[0].")
    add_completion_test("std::vector<std::string> s; s.", True)
    add_completion_test("std::vector<std::string> s; s.back().")
    add_completion_test("std::vector<std::string> s; s[0].")
    add_completion_test("namespace Test { ", True)
    add_completion_test(" ", True)
    add_completion_test("using namespace Test; ", True)
    add_completion_test("using namespace Test;\nusing namespace std; ", True)
    add_completion_test("std::vector<Test::Class1> t; t.", True)
    add_completion_test("using namespace Class1; std::vector<Class1> t; t.", True)
    add_completion_test("using namespace std; vector<Test::Class1> t; t.", True)
    add_completion_test("vector<Test::Class1> t; t.")
    add_completion_test("std::vector<Test::Class1> t; t[0].")
    add_completion_test("std::string s; s.", True, True)
    add_completion_test("blah::", True)
    add_completion_test("std::rel_ops::", True)
    add_completion_test("a::")
    add_completion_test("a::Test2::")
    add_completion_test("a::Test2::Test3::")
    add_completion_test("Test::")
    add_completion_test("Test::Test2::")
    add_completion_test("Test::Test2::Test3::")
    add_completion_test("b::")
    add_completion_test("c::")
    add_completion_test("d::")
    add_completion_test("e::")
    add_completion_test("a::Test2::Test3::T3Class::")
    add_completion_test("b::Test3::T3Class::")
    add_completion_test("c::T3Class::")
    add_completion_test("d::Test3::T3Class::")
    add_completion_test("d::T3Class::")
    add_completion_test("a::T3Class::")
    add_completion_test("e::T3Class::")
    add_completion_test("Test::Test2::Test3::T3Class::")
    add_completion_test("ZZZ::")
    add_completion_test("ZZZ::Class1::")
    add_completion_test("ZZZ::Test3::")
    add_completion_test("ZZZ::T3Class::")
    add_completion_test("ZZZ::Test2::")
    add_completion_test("ZZZ::Test3::T3Class::")
    add_completion_test("ZZZ::z::")
    add_completion_test("void Test::Class1::function(int something) {", True)
    add_completion_test("void Test::Class1::function(Class1 &other) { other.")

    #---------------------------------------------------------

    tu = get_tu("unittests/4.cpp")
    add_completion_test("C c; c.")
    add_completion_test("C c; c->")
    add_completion_test("C c; c[0].")
    add_completion_test("C c; c[0]->")
    add_completion_test("C *c; c[0].")
    add_completion_test("C *c; c[0][0].")
    add_completion_test("C *c; c[0]->")
    add_completion_test("C *c; c->")
    add_completion_test("C *c; c.")
    add_completion_test("void C::something() { singleA.")
    add_completion_test("void C::something() { singleA->")
    add_completion_test("void C::something() { singleA[0].")
    add_completion_test("void C::something() { singleA[0]->")
    add_completion_test("void C::something() { singleA[0][0].")
    add_completion_test("void C::something() { doubleA.")
    add_completion_test("void C::something() { doubleA->")
    add_completion_test("void C::something() { doubleA[0].")
    add_completion_test("void C::something() { doubleA[0]->")
    add_completion_test("void C::something() { doubleA[0][0].")
    add_completion_test("void C::something() { doubleA[0][0]->")
    add_completion_test("void C::something() { doubleA[0][0][0].")
    add_completion_test("void C::something() { tripleA.")
    add_completion_test("void C::something() { tripleA->")
    add_completion_test("void C::something() { tripleA[0].")
    add_completion_test("void C::something() { tripleA[0]->")
    add_completion_test("void C::something() { tripleA[0][0].")
    add_completion_test("void C::something() { tripleA[0][0]->")
    add_completion_test("void C::something() { tripleA[0][0][0].")
    add_completion_test("void C::something() { tripleA[0][0][0]->")
    add_completion_test("void C::something() { tripleA[0][0][0][0].")
    add_completion_test("void C::something() { singleB.")
    add_completion_test("void C::something() { singleB->")
    add_completion_test("void C::something() { singleB[0].")
    add_completion_test("void C::something() { singleB[0]->")
    add_completion_test("void C::something() { singleB[0][0].")
    add_completion_test("void C::something() { doubleB.")
    add_completion_test("void C::something() { doubleB->")
    add_completion_test("void C::something() { doubleB[0].")
    add_completion_test("void C::something() { doubleB[0]->")
    add_completion_test("void C::something() { doubleB[0][0].")
    add_completion_test("void C::something() { doubleB[0][0]->")
    add_completion_test("void C::something() { doubleB[0][0][0].")
    add_completion_test("void C::something() { tripleB.")
    add_completion_test("void C::something() { tripleB->")
    add_completion_test("void C::something() { tripleB[0].")
    add_completion_test("void C::something() { tripleB[0]->")
    add_completion_test("void C::something() { tripleB[0][0].")
    add_completion_test("void C::something() { tripleB[0][0]->")
    add_completion_test("void C::something() { tripleB[0][0][0].")
    add_completion_test("void C::something() { tripleB[0][0][0]->")
    add_completion_test("void C::something() { tripleB[0][0][0][0].")
    add_completion_test("void C::something() { getSingleA().")
    add_completion_test("void C::something() { getSingleA()->")
    add_completion_test("void C::something() { getSingleA()[0].")
    add_completion_test("void C::something() { getSingleA()[0]->")
    add_completion_test("void C::something() { getSingleA()[0][0].")
    add_completion_test("void C::something() { getDoubleA().")
    add_completion_test("void C::something() { getDoubleA()->")
    add_completion_test("void C::something() { getDoubleA()[0].")
    add_completion_test("void C::something() { getDoubleA()[0]->")
    add_completion_test("void C::something() { getDoubleA()[0][0].")
    add_completion_test("void C::something() { getDoubleA()[0][0]->")
    add_completion_test("void C::something() { getDoubleA()[0][0][0].")
    add_completion_test("void C::something() { getTripleA().")
    add_completion_test("void C::something() { getTripleA()->")
    add_completion_test("void C::something() { getTripleA()[0].")
    add_completion_test("void C::something() { getTripleA()[0]->")
    add_completion_test("void C::something() { getTripleA()[0][0].")
    add_completion_test("void C::something() { getTripleA()[0][0]->")
    add_completion_test("void C::something() { getTripleA()[0][0][0].")
    add_completion_test("void C::something() { getTripleA()[0][0][0]->")
    add_completion_test("void C::something() { getTripleA()[0][0][0][0].")
    add_completion_test("void C::something() { asinglemix.")
    add_completion_test("void C::something() { asinglemix->")
    add_completion_test("void C::something() { asinglemix[0].")
    add_completion_test("void C::something() { asinglemix[0]->")
    add_completion_test("void C::something() { asinglemix[0][0].")
    add_completion_test("void C::something() { asinglemix[0][0]->")
    add_completion_test("void C::something() { asinglemix.")
    add_completion_test("void C::something() { adoublemix1->")
    add_completion_test("void C::something() { adoublemix1[0].")
    add_completion_test("void C::something() { adoublemix1[0]->")
    add_completion_test("void C::something() { adoublemix1[0][0].")
    add_completion_test("void C::something() { adoublemix1[0][0]->")
    add_completion_test("void C::something() { adoublemix2->")
    add_completion_test("void C::something() { adoublemix2[0].")
    add_completion_test("void C::something() { adoublemix2[0]->")
    add_completion_test("void C::something() { adoublemix2[0][0].")
    add_completion_test("void C::something() { adoublemix2[0][0]->")
    add_completion_test("quat q; q.")
    add_completion_test("quat q; q.test.")
    add_completion_test("quat::")
    add_completion_test("quat::test2 t; t.")
    add_completion_test("quat q; q.myEnum.")
    add_completion_test("Test2 t2; t2.")
    add_completion_test("Test2 t2; t2.UnionMember.")
    add_completion_test("Test2 t2; t2.EnumMember.")
    add_completion_test("Test2::")
    add_completion_test("void Test2::something() { this->")
    add_completion_test("void Test2::something() { UnionMember.")
    add_completion_test("void Test2::something() { EnumMember.")
    add_completion_test("void Test2::something() { ", True)

    data = read_file("unittests/3.cpp")

    add_completion_test(data + "quat q; q.myEnum.")
    add_completion_test(data + "Test2 t2; t2.")
    add_completion_test(data + "Test2 t2; t2.UnionMember.")
    add_completion_test(data + "Test2 t2; t2.EnumMember.")


    # ---------------------------------------------------------

    tu = get_tu("unittests/5.cpp")
    add_completion_test("sp<A> t; t.")
    add_completion_test("sp<A> t; t.get().")
    add_completion_test("sp<A> t; t.get()->")
    add_completion_test("sp<A> t; t->")
    add_completion_test("sp<A> t; t[0].")
    add_completion_test("sp<A> t; t[0]->")
    add_completion_test("sp<B> t; t.")
    add_completion_test("sp<B> t; t.get().")
    add_completion_test("sp<B> t; t.get()->")
    add_completion_test("sp<B> t; t->")
    add_completion_test("sp<B> t; t[0].")
    add_completion_test("sp<B> t; t[0]->")
    add_completion_test("sp<C> t; t.")
    add_completion_test("sp<C> t; t->")
    add_completion_test("sp<C> t; t.get().")
    add_completion_test("sp<C> t; t.get()->")
    add_completion_test("sp<C> t; t[0].")
    add_completion_test("sp<C> t; t[0]->")
    add_completion_test("sp<A> t; t->afunction().")
    add_completion_test("sp2<A, B> t; t.")
    add_completion_test("sp2<A, B> t; t.funca()->")
    add_completion_test("sp2<A, B> t; t.funcb()->")
    add_completion_test("sp2<A, B> t; t.funca().")
    add_completion_test("sp2<A, B> t; t.funcb().")
    add_completion_test("C c; c.")
    add_completion_test("C c; c.m_sp2.")
    add_completion_test("C c; c.m_sp2.funca()->")
    add_completion_test("C c; c.m_sp2.funcb()->")
    add_completion_test("C c; c.m_sp2.funca().")
    add_completion_test("C c; c.m_sp2.funcb().")

    # ---------------------------------------------------------

    tu = get_tu("unittests/6.cpp")
    add_completion_test(" ", True)
    add_completion_test("myenum::")
    add_completion_test("myenum e; e.")
    add_completion_test("m.")
    add_completion_test("m s; s.")
    add_completion_test("mystruct2 s; s.")
    add_completion_test("A::")
    add_completion_test("A a; a.")
    add_completion_test("A a; a.f.")
    add_completion_test("A a; a.i.")
    add_completion_test("A a; a.ms.")
    add_completion_test("MyStaticClass c; c.")
    add_completion_test("MyStaticClass::")
    add_completion_test("void MyStaticClass::something() { MyStaticClass::")
    add_completion_test("void MyStaticClass::something() { this->")
    add_completion_test("Child::")
    add_completion_test("void Child::something() { MyStaticClass::")
    add_completion_test("void Child::something() { Child::")
    add_completion_test("void Child::something() { this->")
    add_completion_test("void A::something() {")

    data = read_file("unittests/6.cpp")
    add_completion_test(data + " ")
    add_completion_test(data + " myenum::")
    add_completion_test(data + " m.")
    add_completion_test(data + " A::")

    # ---------------------------------------------------------

    tu = get_tu("unittests/7.cpp")
    add_completion_test("A a; a.")
    add_completion_test("AArray.")
    add_completion_test("AArray[0].")
    add_completion_test("AArray test; test.")
    add_completion_test("AArray test; test[0].")
    add_completion_test("AArray *test; test.")
    add_completion_test("AArray *test; test[0].")
    add_completion_test("AArray *test; test[0][0].")
    add_completion_test("Test t; t.")
    add_completion_test("Test t; t.a.")
    add_completion_test("Test t; t.array.")
    add_completion_test("Test t; t.array[0].")
    add_completion_test("TestStruct i; i.")
    add_completion_test("TestStruct::")
    add_completion_test("TestStruct2::")
    add_completion_test("TS.")
    add_completion_test("TS[0].")
    add_completion_test("TS t; t.")
    add_completion_test("TS t; t[0].")
    add_completion_test("Test t[10]; t.")
    add_completion_test("Test t[10]; t[0].")
    add_completion_test("Test t[10][20]; t.")
    add_completion_test("Test t[10][20]; t[0].")
    add_completion_test("Test t[10][20]; t[0][0].")
    add_completion_test("Test *t[20]; t[0][0].")
    add_completion_test("Test *t[20]; t[0].")
    add_completion_test("Test *t[20]; t.")
    add_completion_test("size_t t; t.")
    add_completion_test("TestStruct2::MyClass::")
    add_completion_test("TestStruct2::MyClass m; m.")
    add_completion_test("TestStruct2::MyStruct::")
    add_completion_test("TestStruct2::MyStruct m; m.")
    add_completion_test("TestStruct2::MyEnum::")
    add_completion_test("TestStruct2::MyEnum e; e.")
    add_completion_test("void TestStruct2::blah() { someMember.")

    data = read_file("unittests/7.cpp")
    subdata = data[:data.rfind("*t;")+4]
    add_completion_test(subdata + "t.")
    add_completion_test(subdata + "t->")

    subdata = data[:data.rfind(" a;")+4]
    add_completion_test(subdata + "a.")
    add_completion_test(subdata + "a->")
    add_completion_test(data + "c.")
    add_completion_test(data + "b.")
    add_completion_test(data + "i.")

    # ---------------------------------------------------------

    opts = [
                "-isysroot",
                "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.7.sdk/",
                "-F/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.7.sdk/System/Library/Frameworks",
                "-ICocoa"]
    tu = get_tu("unittests/8.mm")
    add_completion_test(" ", True)
    add_completion_test("[Hello ")
    add_completion_test("Hello * h; [h ")
    add_completion_test("World * w; [w ")
    add_completion_test("World * w; [[w world] ")
    add_completion_test("World * w; [[w blah] ")
    add_completion_test("World2 * w; [[w world2] ")
    add_completion_test("World2 * w; [[[w world2] world] ")
    add_completion_test("World2 * w; w.")
    add_completion_test("World2 * w; w.world2.")
    add_completion_test("World2 * w; w.world2.world.")
    add_completion_test("""@implementation World2
    - (World*) world2
    {
    [self """)
    add_completion_test("""@implementation World2
    - (World*) world2
    {
        self.""")

    add_completion_test("World3 *w; w.")
    add_completion_test("World3 *w; [w ")
    add_completion_test("World3 *w; w->")
    add_completion_test("World *w; w.")
    add_completion_test("World *w; w->")
    add_completion_test("World *w; w.world.")
    add_completion_test("World *w; w.world->")
    add_completion_test("World *w; w->worldVar.")
    add_completion_test("World *w; w->worldVar->")

    data = read_file("unittests/8.mm")
    add_completion_test(data[:data.rfind(".")+1])
    add_completion_test("""@implementation World3
    - (void) something
    {
        """, True)

    add_completion_test("""@implementation World4
    - (void) myworld
    {
        """, True)
    add_completion_test("World4 *w; w.")
    add_completion_test("World4 *w; w->")
    add_completion_test("World4 *w; [w ")

    add_completion_test("World5 *w; [w ")

    # ---------------------------------------------------------


    if platform.system() == "Darwin":
        tu = get_tu("unittests/9.mm")
        add_completion_test("[NSString ", True)
        add_completion_test("NSString *s; [s ", True)

        add_completion_test("[NSMutableData ", True)
        add_completion_test("NSMutableData *s; [s ", True)

        add_completion_test("Test t; [t.", True)
        add_completion_test("Test t; [t.context ", True)


    # ---------------------------------------------------------

    tu = get_tu("unittests/10.cpp")
    add_completion_test("new nms::")
    add_completion_test("function().")
    add_completion_test("function()->")
    add_completion_test("function2().")
    add_completion_test("function2()->")
    add_completion_test("ifunction().")
    add_completion_test("ifunction()->")
    add_completion_test("ifunction2().")
    add_completion_test("ifunction2()->")
    add_completion_test("a1.")
    add_completion_test("a1->")
    add_completion_test("a2.")
    add_completion_test("a2->")
    add_completion_test("nms::function().")
    add_completion_test("nms::function()->")
    add_completion_test("nms::function2().")
    add_completion_test("nms::function2()->")
    add_completion_test("nms::ffunction().")
    add_completion_test("nms::ffunction()->")
    add_completion_test("nms::ffunction2().")
    add_completion_test("nms::ffunction2()->")
    add_completion_test("nms::z1.")
    add_completion_test("nms::z1->")
    add_completion_test("nms::z2.")
    add_completion_test("nms::z2->")
    add_completion_test("using namespace nms; zfunction().")
    add_completion_test("using namespace nms; zfunction()->")
    add_completion_test("using namespace nms; zfunction2().")
    add_completion_test("using namespace nms; zfunction2()->")
    add_completion_test("using namespace nms; z1.")
    add_completion_test("using namespace nms; z1->")
    add_completion_test("using namespace nms; z2.")
    add_completion_test("using namespace nms; z2->")
    add_completion_test("void A::something() { function().")
    add_completion_test("B::getInstance()->")
    add_completion_test("TES")

    # ---------------------------------------------------------

if (testsAdded or update) and not dryrun:
    f = gzip.GzipFile(GOLDFILE, "wb")
    pickle.dump(golden, f, -1)
    f.close()

print "All is well"
