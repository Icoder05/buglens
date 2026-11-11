# Error analysis: S6 (test)

40 of 300 instances miss the gold file in the top 5. Showing 20 (random, seed 42). Fill in `Category:` (e.g. vague issue, multi-file, test-only hint, wrong module, ranking).

## django__django-16400

**Issue (excerpt):** migrate management command does not respect database parameter when adding Permissions. Description 	  		(last modified by Vasanth) 	  When invoking migrate with a database parameter, the migration runs successfully. However, there seems to be a DB read request that runs after the migration. This call does not respect the db param and invokes the db router . When naming the db as a parameter, all DB calls in the context of the migrate command are expected to use the database specified. I came across this as I am currently using a thread-local variable to get the active DB with a custom DB rout

**Gold files:** `django/contrib/auth/management/__init__.py`  
**Gold functions:** `django/contrib/auth/management/__init__.py::create_permissions`

**Top-5 predictions:**

1. `django/core/management/commands/migrate.py::Command.handle`
2. `django/db/utils.py::ConnectionRouter.allow_migrate`
3. `django/core/management/commands/migrate.py::<module>`
4. `django/db/models/manager.py::BaseManager.db`
5. `django/db/migrations/operations/base.py::Operation.allow_migrate_model`

Category: 

## django__django-11797

**Issue (excerpt):** Filtering on query result overrides GROUP BY of internal query Description 	 from django.contrib.auth import models a = models.User.objects.filter(email__isnull=True).values('email').annotate(m=Max('id')).values('m') print(a.query) # good # SELECT MAX("auth_user"."id") AS "m" FROM "auth_user" WHERE "auth_user"."email" IS NULL GROUP BY "auth_user"."email" print(a[:1].query) # good # SELECT MAX("auth_user"."id") AS "m" FROM "auth_user" WHERE "auth_user"."email" IS NULL GROUP BY "auth_user"."email" LIMIT 1 b = models.User.objects.filter(id=a[:1]) print(b.query) # GROUP BY U0."id" should be GROUP 

**Gold files:** `django/db/models/lookups.py`  
**Gold functions:** `django/db/models/lookups.py::Exact.process_rhs`

**Top-5 predictions:**

1. `django/db/models/sql/query.py::Query.set_group_by`
2. `django/db/models/sql/query.py::Query.get_aggregation`
3. `django/db/models/query.py::QuerySet._earliest`
4. `django/db/models/query.py::QuerySet.aggregate`
5. `django/db/models/query.py::QuerySet.annotate`

Category: 

## django__django-17087

**Issue (excerpt):** Class methods from nested classes cannot be used as Field.default. Description 	  		(last modified by Mariusz Felisiak) 	  Given the following model:   class Profile(models.Model): 	class Capability(models.TextChoices): 		BASIC = ("BASIC", "Basic") 		PROFESSIONAL = ("PROFESSIONAL", "Professional") 		 		@classmethod 		def default(cls) -> list[str]: 			return [cls.BASIC] 	capabilities = ArrayField( 		models.CharField(choices=Capability.choices, max_length=30, blank=True), 		null=True, 		default=Capability.default 	) The resulting migration contained the following:  # ... 	 migrations.AddField( 	

**Gold files:** `django/db/migrations/serializer.py`  
**Gold functions:** `django/db/migrations/serializer.py::FunctionTypeSerializer.serialize`

**Top-5 predictions:**

1. `django/db/migrations/operations/fields.py::AddField.reduce`
2. `django/db/migrations/operations/fields.py::AddField.deconstruct`
3. `django/contrib/postgres/fields/ranges.py::RangeField.__init__`
4. `django/db/migrations/operations/fields.py::AddField.database_forwards`
5. `django/db/migrations/operations/fields.py::RemoveField.reduce`

Category: 

## sympy__sympy-20590

**Issue (excerpt):** Symbol instances have __dict__ since 1.7? In version 1.6.2 Symbol instances had no `__dict__` attribute ```python >>> sympy.Symbol('s').__dict__ --------------------------------------------------------------------------- AttributeError                            Traceback (most recent call last) <ipython-input-3-e2060d5eec73> in <module> ----> 1 sympy.Symbol('s').__dict__  AttributeError: 'Symbol' object has no attribute '__dict__' >>> sympy.Symbol('s').__slots__ ('name',) ```  This changes in 1.7 where `sympy.Symbol('s').__dict__` now exists (and returns an empty dict) I may mis

**Gold files:** `sympy/core/_print_helpers.py`  
**Gold functions:** `sympy/core/_print_helpers.py::Printable`

**Top-5 predictions:**

1. `sympy/codegen/ast.py::Token.__new__`
2. `sympy/core/symbol.py::_symbol`
3. `sympy/polys/polyutils.py::PicklableWithSlots.__setstate__`
4. `sympy/core/containers.py::Dict`
5. `sympy/core/function.py::UndefinedFunction.__new__`

Category: 

## sympy__sympy-12236

**Issue (excerpt):** Wrong result with apart ``` Python 3.6.0 |Continuum Analytics, Inc.| (default, Dec 23 2016, 12:22:00)  Type "copyright", "credits" or "license" for more information.  IPython 5.1.0 -- An enhanced Interactive Python. ?         -> Introduction and overview of IPython's features. %quickref -> Quick reference. help      -> Python's own help system. object?   -> Details about 'object', use 'object??' for extra details.  In [1]: from sympy import symbols  In [2]: a = symbols('a', real=True)  In [3]: t = symbols('t', real=True, negative=False)  In [4]: bug = a * (-t + (-t + 1) * (2 * 

**Gold files:** `sympy/polys/domains/polynomialring.py`  
**Gold functions:** `sympy/polys/domains/polynomialring.py::PolynomialRing.from_FractionField`

**Top-5 predictions:**

1. `sympy/interactive/session.py::init_session`
2. `sympy/polys/partfrac.py::apart`
3. `sympy/interactive/session.py::<module>`
4. `sympy/interactive/printing.py::_is_ipython`
5. `sympy/core/expr.py::Expr.apart`

Category: 

## sphinx-doc__sphinx-8627

**Issue (excerpt):** autodoc isn't able to resolve struct.Struct type annotations **Describe the bug** If `struct.Struct` is declared in any type annotations, I get `class reference target not found: Struct`  **To Reproduce** Simple `index.rst` ``` Hello World ===========  code docs =========  .. automodule:: helloworld.helloworld ```  Simple `helloworld.py` ``` import struct import pathlib  def consume_struct(_: struct.Struct) -> None:     pass  def make_struct() -> struct.Struct:     mystruct = struct.Struct('HH')     return mystruct  def make_path() -> pathlib.Path:     return pathli

**Gold files:** `sphinx/util/typing.py`  
**Gold functions:** `sphinx/util/typing.py::<module>`, `sphinx/util/typing.py::restify`, `sphinx/util/typing.py::stringify`

**Top-5 predictions:**

1. `sphinx/ext/autodoc/__init__.py::DocstringSignatureMixin._find_signature`
2. `sphinx/ext/autodoc/__init__.py::Documenter.__init__`
3. `sphinx/ext/autodoc/__init__.py::ModuleLevelDocumenter.resolve_name`
4. `sphinx/ext/autodoc/__init__.py::AttributeDocumenter.update_annotations`
5. `sphinx/ext/autodoc/__init__.py::MethodDocumenter.annotate_to_first_argument`

Category: 

## sympy__sympy-14024

**Issue (excerpt):** Inconsistency when simplifying (-a)**x * a**(-x), a a positive integer Compare:  ``` >>> a = Symbol('a', integer=True, positive=True) >>> e = (-a)**x * a**(-x) >>> f = simplify(e) >>> print(e) a**(-x)*(-a)**x >>> print(f) (-1)**x >>> t = -S(10)/3 >>> n1 = e.subs(x,t) >>> n2 = f.subs(x,t) >>> print(N(n1)) -0.5 + 0.866025403784439*I >>> print(N(n2)) -0.5 + 0.866025403784439*I ```  vs  ``` >>> a = S(2) >>> e = (-a)**x * a**(-x) >>> f = simplify(e) >>> print(e) (-2)**x*2**(-x) >>> print(f) (-1)**x >>> t = -S(10)/3 >>> n1 = e.subs(x,t) >>> n2 = f.subs(x,t) >>> print(

**Gold files:** `sympy/core/numbers.py`  
**Gold functions:** `sympy/core/numbers.py::Rational._eval_power`, `sympy/core/numbers.py::Integer._eval_power`

**Top-5 predictions:**

1. `sympy/simplify/fu.py::as_f_sign_1`
2. `sympy/simplify/simplify.py::posify`
3. `sympy/simplify/simplify.py::signsimp`
4. `sympy/simplify/simplify.py::sum_add`
5. `sympy/simplify/fu.py::TR10i`

Category: 

## matplotlib__matplotlib-25311

**Issue (excerpt):** [Bug]: Unable to pickle figure with draggable legend ### Bug summary  I am unable to pickle figure with draggable legend. Same error comes for draggable annotations.      ### Code for reproduction  ```python import matplotlib.pyplot as plt import pickle  fig = plt.figure() ax = fig.add_subplot(111)  time=[0,1,2,3,4] speed=[40,43,45,47,48]  ax.plot(time,speed,label="speed")  leg=ax.legend() leg.set_draggable(True) #pickling works after removing this line   pickle.dumps(fig) plt.show() ```   ### Actual outcome  `TypeError: cannot pickle 'FigureCanvasQTAgg' object`

**Gold files:** `lib/matplotlib/offsetbox.py`  
**Gold functions:** `lib/matplotlib/offsetbox.py::DraggableBase.__init__`, `lib/matplotlib/offsetbox.py::DraggableBase`

**Top-5 predictions:**

1. `lib/matplotlib/backends/backend_qtagg.py::FigureCanvasQTAgg.paintEvent`
2. `lib/matplotlib/backends/backend_qtagg.py::FigureCanvasQTAgg`
3. `lib/matplotlib/backends/backend_qtagg.py::FigureCanvasQTAgg.print_figure`
4. `lib/matplotlib/backends/backend_qtagg.py::_BackendQTAgg`
5. `lib/matplotlib/figure.py::Figure.__getstate__`

Category: 

## django__django-12470

**Issue (excerpt):** Inherited model doesn't correctly order by "-pk" when specified on Parent.Meta.ordering Description 	 Given the following model definition: from django.db import models class Parent(models.Model): 	class Meta: 		ordering = ["-pk"] class Child(Parent): 	pass Querying the Child class results in the following: >>> print(Child.objects.all().query) SELECT "myapp_parent"."id", "myapp_child"."parent_ptr_id" FROM "myapp_child" INNER JOIN "myapp_parent" ON ("myapp_child"."parent_ptr_id" = "myapp_parent"."id") ORDER BY "myapp_parent"."id" ASC The query is ordered ASC but I expect the order to be DESC.

**Gold files:** `django/db/models/sql/compiler.py`  
**Gold functions:** `django/db/models/sql/compiler.py::SQLCompiler.find_ordering_name`

**Top-5 predictions:**

1. `django/db/models/base.py::Model._get_next_or_previous_in_order`
2. `django/db/models/options.py::Options._prepare`
3. `django/db/models/base.py::Model._check_ordering`
4. `django/db/models/fields/related.py::ForeignObject.get_instance_value_for_fields`
5. `django/db/models/base.py::Model._check_field_name_clashes`

Category: 

## sympy__sympy-17022

**Issue (excerpt):** Lambdify misinterprets some matrix expressions Using lambdify on an expression containing an identity matrix gives us an unexpected result:  ```python >>> import numpy as np >>> n = symbols('n', integer=True) >>> A = MatrixSymbol("A", n, n) >>> a = np.array([[1, 2], [3, 4]]) >>> f = lambdify(A, A + Identity(n)) >>> f(a) array([[1.+1.j, 2.+1.j],        [3.+1.j, 4.+1.j]]) ```  Instead, the output should be  `array([[2, 2], [3, 5]])`, since we're adding an identity matrix to the array. Inspecting the globals and source code of `f` shows us why we get the result:  ```python >>> imp

**Gold files:** `sympy/printing/pycode.py`  
**Gold functions:** `sympy/printing/pycode.py::NumPyPrinter`

**Top-5 predictions:**

1. `sympy/utilities/lambdify.py::lambdify`
2. `sympy/plotting/experimental_lambdify.py::<module>`
3. `sympy/utilities/lambdify.py::lambdastr`
4. `sympy/plotting/experimental_lambdify.py::Lambdifier.str2tree`
5. `sympy/utilities/lambdify.py::_EvaluatorPrinter._preprocess`

Category: 

## pytest-dev__pytest-7168

**Issue (excerpt):** INTERNALERROR when exception in __repr__ Minimal code to reproduce the issue:  ```python class SomeClass:     def __getattribute__(self, attr):         raise     def __repr__(self):         raise def test():     SomeClass().attr ``` Session traceback: ``` ============================= test session starts ============================== platform darwin -- Python 3.8.1, pytest-5.4.1, py-1.8.1, pluggy-0.13.1 -- /usr/local/opt/python@3.8/bin/python3.8 cachedir: .pytest_cache rootdir: ****** plugins: asyncio-0.10.0, mock-3.0.0, cov-2.8.1 collecting ... collected 1 item  test_pytes

**Gold files:** `src/_pytest/_io/saferepr.py`  
**Gold functions:** `src/_pytest/_io/saferepr.py::_format_repr_exception`

**Top-5 predictions:**

1. `src/_pytest/_code/code.py::<module>`
2. `src/_pytest/config/__init__.py::Config.notify_exception`
3. `src/_pytest/main.py::Session.__repr__`
4. `src/_pytest/main.py::Session._collect`
5. `src/_pytest/main.py::wrap_session`

Category: 

## sympy__sympy-13895

**Issue (excerpt):** (-x/4 - S(1)/12)**x - 1 simplifies to an inequivalent expression     >>> from sympy import *     >>> x = Symbol('x')     >>> e = (-x/4 - S(1)/12)**x - 1     >>> e     (-x/4 - 1/12)**x - 1     >>> f = simplify(e)     >>> f     12**(-x)*(-12**x + (-3*x - 1)**x)     >>> a = S(9)/5     >>> simplify(e.subs(x,a))     -1 - 32*15**(1/5)*2**(2/5)/225     >>> simplify(f.subs(x,a))     -1 - 32*(-1)**(4/5)*60**(1/5)/225     >>> N(e.subs(x,a))     -1.32255049319339     >>> N(f.subs(x,a))     -0.739051169462523 - 0.189590423018741*I

**Gold files:** `sympy/core/numbers.py`  
**Gold functions:** `sympy/core/numbers.py::Integer._eval_power`

**Top-5 predictions:**

1. `sympy/simplify/fu.py::TR3`
2. `sympy/simplify/simplify.py::signsimp`
3. `sympy/simplify/radsimp.py::fraction`
4. `sympy/simplify/simplify.py::nthroot`
5. `sympy/simplify/fu.py::TR12i`

Category: 

## scikit-learn__scikit-learn-25500

**Issue (excerpt):** CalibratedClassifierCV doesn't work with `set_config(transform_output="pandas")` ### Describe the bug  CalibratedClassifierCV with isotonic regression doesn't work when we previously set `set_config(transform_output="pandas")`. The IsotonicRegression seems to return a dataframe, which is a problem for `_CalibratedClassifier`  in `predict_proba` where it tries to put the dataframe in a numpy array row `proba[:, class_idx] = calibrator.predict(this_pred)`.  ### Steps/Code to Reproduce  ```python import numpy as np from sklearn import set_config from sklearn.calibration import Calibrate

**Gold files:** `sklearn/isotonic.py`  
**Gold functions:** `sklearn/isotonic.py::IsotonicRegression.transform`, `sklearn/isotonic.py::IsotonicRegression`, `sklearn/isotonic.py::IsotonicRegression.predict`

**Top-5 predictions:**

1. `sklearn/calibration.py::CalibratedClassifierCV`
2. `sklearn/calibration.py::CalibratedClassifierCV.predict`
3. `sklearn/calibration.py::CalibratedClassifierCV.fit`
4. `sklearn/calibration.py::CalibratedClassifierCV.__init__`
5. `sklearn/calibration.py::_CalibratedClassifier`

Category: 

## pylint-dev__pylint-7080

**Issue (excerpt):** `--recursive=y` ignores `ignore-paths` ### Bug description  When running recursively, it seems `ignore-paths` in my settings in pyproject.toml is completely ignored  ### Configuration  ```ini [tool.pylint.MASTER] ignore-paths = [   # Auto generated   "^src/gen/.*$", ] ```   ### Command used  ```shell pylint --recursive=y src/ ```   ### Pylint output  ```shell ************* Module region_selection src\region_selection.py:170:0: R0914: Too many local variables (17/15) (too-many-locals) ************* Module about src\gen\about.py:2:0: R2044: Line with empty comment (em

**Gold files:** `pylint/lint/expand_modules.py`  
**Gold functions:** `pylint/lint/expand_modules.py::_is_ignored_file`

**Top-5 predictions:**

1. `pylint/pyreverse/main.py::Run.run`
2. `pylint/config/arguments_manager.py::_ArgumentsManager._generate_config_file`
3. `pylint/config/_pylint_config/generate_command.py::generate_interactive_config`
4. `pylint/testutils/_primer/primer_run_command.py::RunCommand._lint_package`
5. `pylint/lint/run.py::Run.__init__`

Category: 

## matplotlib__matplotlib-25332

**Issue (excerpt):** [Bug]: Unable to pickle figure with aligned labels ### Bug summary   Unable to pickle figure after calling `align_labels()`  ### Code for reproduction  ```python import matplotlib.pyplot as plt import pickle  fig = plt.figure() ax1 = fig.add_subplot(211) ax2 = fig.add_subplot(212) time=[0,1,2,3,4] speed=[40000,4300,4500,4700,4800] acc=[10,11,12,13,14] ax1.plot(time,speed) ax1.set_ylabel('speed') ax2.plot(time,acc) ax2.set_ylabel('acc')  fig.align_labels() ##pickling works after removing this line   pickle.dumps(fig) plt.show() ```   ### Actual outcome ``` align.py

**Gold files:** `lib/matplotlib/cbook.py`  
**Gold functions:** `lib/matplotlib/cbook.py::Grouper`

**Top-5 predictions:**

1. `lib/matplotlib/figure.py::FigureBase.align_ylabels`
2. `lib/matplotlib/figure.py::FigureBase.align_xlabels`
3. `lib/matplotlib/figure.py::FigureBase.align_labels`
4. `lib/matplotlib/axis.py::Axis.__init__`
5. `lib/matplotlib/figure.py::FigureBase.autofmt_xdate`

Category: 

## sympy__sympy-18087

**Issue (excerpt):** Simplify of simple trig expression fails trigsimp in various versions, including 1.5, incorrectly simplifies cos(x)+sqrt(sin(x)**2) as though it were cos(x)+sin(x) for general complex x. (Oddly it gets this right if x is real.)  Embarrassingly I found this by accident while writing sympy-based teaching material...

**Gold files:** `sympy/core/exprtools.py`  
**Gold functions:** `sympy/core/exprtools.py::Factors.__init__`, `sympy/core/exprtools.py::Factors.as_expr`

**Top-5 predictions:**

1. `sympy/simplify/trigsimp.py::exptrigsimp`
2. `sympy/simplify/trigsimp.py::__trigsimp`
3. `sympy/simplify/trigsimp.py::trigsimp`
4. `sympy/simplify/trigsimp.py::trigsimp_old`
5. `sympy/simplify/trigsimp.py::_futrig`

Category: 

## sympy__sympy-20322

**Issue (excerpt):** Inconsistent behavior for sympify/simplify with ceiling In sympy v1.5.1: ```python In [16]: sympy.sympify('4*ceiling(x/4 - 3/4)', evaluate=False).simplify() Out[16]: 4*ceiling(x/4 - 3/4)  In [17]: sympy.sympify('4*ceiling(x/4 - 3/4)', evaluate=True).simplify() Out[17]: 4*ceiling(x/4 - 3/4) ```  In sympy v.1.6.2: ```python In [16]: sympy.sympify('4*ceiling(x/4 - 3/4)', evaluate=False).simplify() Out[16]: 4*ceiling(x/4) - 3  In [17]: sympy.sympify('4*ceiling(x/4 - 3/4)', evaluate=True).simplify() Out [17]: 4*ceiling(x/4 - 3/4) ```  Is there a way to ensure that the behavior is 

**Gold files:** `sympy/core/mul.py`  
**Gold functions:** `sympy/core/mul.py::<module>`, `sympy/core/mul.py::Mul`, `sympy/core/mul.py::Mul._eval_is_integer`

**Top-5 predictions:**

1. `sympy/concrete/expr_with_limits.py::_common_new`
2. `sympy/simplify/hyperexpand.py::try_polynomial`
3. `sympy/simplify/hyperexpand.py::UnShiftA.__init__`
4. `sympy/concrete/expr_with_limits.py::_process_limits`
5. `sympy/logic/boolalg.py::And._eval_simplify`

Category: 

## sympy__sympy-12419

**Issue (excerpt):** Sum of the elements of an identity matrix is zero I think this is a bug.  I created a matrix by M.T * M under an assumption that M is orthogonal.  SymPy successfully recognized that the result is an identity matrix.  I tested its identity-ness by element-wise, queries, and sum of the diagonal elements and received expected results.  However, when I attempt to evaluate the total sum of the elements the result was 0 while 'n' is expected.  ``` from sympy import * from sympy import Q as Query  n = Symbol('n', integer=True, positive=True) i, j = symbols('i j', integer=True) M = MatrixS

**Gold files:** `sympy/matrices/expressions/matexpr.py`  
**Gold functions:** `sympy/matrices/expressions/matexpr.py::<module>`, `sympy/matrices/expressions/matexpr.py::MatrixElement._eval_derivative`, `sympy/matrices/expressions/matexpr.py::Identity._entry`

**Top-5 predictions:**

1. `sympy/matrices/expressions/trace.py::trace`
2. `sympy/matrices/expressions/determinant.py::refine_Determinant`
3. `sympy/matrices/expressions/matmul.py::refine_MatMul`
4. `sympy/matrices/expressions/matpow.py::MatPow.doit`
5. `sympy/matrices/dense.py::eye`

Category: 

## matplotlib__matplotlib-25433

**Issue (excerpt):** [Bug]: using clf and pyplot.draw in range slider on_changed callback blocks input to widgets ### Bug summary  When using clear figure, adding new widgets and then redrawing the current figure in the on_changed callback of a range slider the inputs to all the widgets in the figure are blocked. When doing the same in the button callback on_clicked, everything works fine.  ### Code for reproduction  ```python import matplotlib.pyplot as pyplot import matplotlib.widgets as widgets  def onchanged(values):     print("on changed")     print(values)     pyplot.clf()     addElements()     pyplo

**Gold files:** `lib/matplotlib/figure.py`  
**Gold functions:** `lib/matplotlib/figure.py::FigureBase.delaxes`

**Top-5 predictions:**

1. `lib/matplotlib/widgets.py::RangeSlider.on_changed`
2. `lib/matplotlib/widgets.py::RangeSlider`
3. `lib/matplotlib/widgets.py::RangeSlider.set_val`
4. `lib/matplotlib/widgets.py::RangeSlider._update`
5. `lib/matplotlib/widgets.py::RangeSlider.__init__`

Category: 

## pytest-dev__pytest-7220

**Issue (excerpt):** Wrong path to test file when directory changed in fixture Files are shown as relative to new directory when working directory is changed in a fixture. This makes it impossible to jump to the error as the editor is unaware of the directory change. The displayed directory should stay relative to the original directory.  test_path_error.py: ```python import os import errno import shutil  import pytest   @pytest.fixture def private_dir():  # or (monkeypatch)     out_dir = 'ddd'      try:         shutil.rmtree(out_dir)     except OSError as ex:         if ex.errno != errno.ENOENT:

**Gold files:** `src/_pytest/nodes.py`  
**Gold functions:** `src/_pytest/nodes.py::<module>`, `src/_pytest/nodes.py::Node._repr_failure_py`

**Top-5 predictions:**

1. `src/_pytest/config/findpaths.py::determine_setup`
2. `src/_pytest/monkeypatch.py::MonkeyPatch.chdir`
3. `src/_pytest/pytester.py::Testdir.getpathnode`
4. `src/_pytest/_code/code.py::Code.path`
5. `testing/python/fixtures.py::TestParameterizedSubRequest.test_non_relative_path`

Category: 
