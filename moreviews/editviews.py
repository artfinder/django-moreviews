"""
Simple, well-documented, class-based views for Django editing that
aren't supported out of the box. We talk about "bound objects" or
"objects bound to <thing>" when there's a ForeignKey from the objects
to <thing>; these objects are also referred to as "children" (and
<thing> as the "parent").

The classes you want are:

  BoundCreateView -- create an object bound to View.object
  MultiCreateView -- create an object with multiple children
  MultiBoundCreateView -- create a bound object with multiple children
  MultiUpdateView -- update an object with multiple children

Use these with CreateView (create an unbound object), UpdateView
(update an object without children) and DeleteView (delete both bound
and unbound objects).
"""

from django import forms
from django.forms.models import modelformset_factory
from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseRedirect
from django.views.generic.base import View
from django.views.generic.edit import FormMixin, ModelFormMixin, ProcessFormView, UpdateView, CreateView
from django.views.generic.detail import SingleObjectTemplateResponseMixin


def bound_object_form(_model, field, initial, form=None):
    """
    Return a ModelForm for `_model` with (ForeignKey) `field` always
    set to `initial`, using `form` or the default ModelForm.

    If `initial` is callable, the result is used. This allows you
    to defer figuring out which object is the parent until you
    save the form, which means you can create subordinate objects
    and their parent object in the same POST.
    """

    if form is None:
        class form(forms.ModelForm):
            class Meta:
                model = _model

    excludes = getattr(form.Meta, 'exclude', (field,))
    if field not in excludes:
        excludes = list(excludes)
        excludes.append(field)
        excludes = tuple(excludes)

    class _form(form):
        def save(self, commit=True):
            obj = super(_form, self).save(commit=False)
            if callable(initial):
                setattr(obj, field, initial())
            else:
                setattr(obj, field, initial)
            if commit:
                obj.save()
            return obj

        class Meta:
            model = form.Meta.model
            exclude = excludes

    return _form


def bound_object_formset(_model, queryset, field, initial, form=None, **factory_kwargs):
    """
    Return a ModelFormSet for `_model` with (ForeignKey) `field` always
    set to `initial`, using `form` or the default ModelForm, and
    working with `queryset` objects (which should be already bound
    to `initial` or you're going to change them all on save).

    As with `bound_object_form`, if `initial` is callable, the result
    rather than the value is used.

    Additional arguments are passed to `modelformset_factory` (so things
    like `can_delete` are useful).
    """

    #print _model, queryset, field, initial, form, factory_kwargs

    # if factory_kwargs['exclude'] is set, it will override the
    # exclude we set on the form (in bound_object_form), so add in
    # field automatically
    if 'exclude' in factory_kwargs:
        if field not in factory_kwargs['exclude']:
            factory_kwargs['exclude'].append(field)

    def construct(*args, **kwargs):
        kwargs.update(
            {
                'queryset': queryset,
                },
            )
        return modelformset_factory(
            model=_model,
            form=bound_object_form(_model, field, initial, form),
            **factory_kwargs
            )(*args, **kwargs)

    return construct


class BoundCreateView(
    SingleObjectTemplateResponseMixin,
    ModelFormMixin,
    ProcessFormView):
    """
    View for creating an object that's 'bound' to another by a
    ForeignKey. For instance if you have:

    class Parent(models.Model):
    	name = models.CharField(max_length=20)

    class Child(models.Model):
    	name = models.CharField(max_length=20)
    	parent = models.ForeignKey(Parent)
    
    then you can use BoundCreateView to make a Child object
    by using a URL with a `pk` variable (in the normal SingleObjectMixin
    way), and setting the following on the BoundCreateView either
    as URL parameters or by subclassing the view:

    model = Child
    bound_field = 'parent'
    queryset = Parent.objects.all() # or whatever makes sense

    The template used will be based on both the bound object and the
    created object. Assuming the parent is app1.parent and the child
    is app2.child, we look in the following order:

    app1/parent_child_create.html
    app2/parent_child_create.html
    app2/child_create.html
    app1/child_create.html
    
    That may be a slightly unexpected order, but if you can't work
    with it you can always override `get_template_names` yourself.
    The "_create" bit uses `template_name_suffix`.

    Other mixins that define `get_template_names` and are after this
    class in the MRO get their stuff at the end. (This includes
    app1/parent.html, which presumably comes from the superclasses of
    BoundCreateView although I haven't tracked it down yet.)

    On success, we redirect to `success_url` on the view, or
    `get_absolute_url()` on the created child; on failure we redisplay
    the form with errors (these are both the 'normal' Django way with
    Class-Based Views).
    """

    # for documentation purposes; declared and defaulted in superclasses
    #form_class = None # will be created automatically otherwise
    #model = None # model of the child
    #queryset = None # queryset for the parent
    template_name_suffix = '_create'
    bound_field = None # the name of the child's ForeignKey to the parent

    def get_form_class(self):
        self.object = self.get_object()
        return bound_object_form(
            self.model,
            field=self.bound_field,
            initial=self.get_object,
            form=self.form_class
            )

    def get_form(self, form_class):
        return form_class(
            prefix='core-object',
            **self.get_form_kwargs()
            )

    def get_form_kwargs(self):
        # ModelFormMixin puts self.object in there as the instance,
        # which is unhelpful for a creation form. BaseCreateView
        # nukes self.object, but we want it at all points other than
        # this, so we do it here and only temporarily.
        _object = self.object
        self.object = None
        kwargs = super(BoundCreateView, self).get_form_kwargs()
        self.object = _object
        return kwargs

    def get_template_names(self):
        """Return a list of templates names to try."""

        try:
            names = super(BoundCreateView, self).get_template_names()
        except ImproperlyConfigured:
            # If template_name isn't specified, it's not a problem --
            # we just start with an empty list.
            names = []

        if self.object and hasattr(self.object, '_meta') and self.model and hasattr(self.model, '_meta'):
            parent_app = self.object._meta.app_label
            parent_object_name = self.object._meta.object_name.lower()
            child_app = self.model._meta.app_label
            child_object_name = self.model._meta.object_name.lower()

            names.insert(0, "%s/%s%s.html" % (parent_app, child_object_name, self.template_name_suffix))
            names.insert(0, "%s/%s%s.html" % (child_app, child_object_name, self.template_name_suffix))
            names.insert(0, "%s/%s_%s%s.html" % (child_app, parent_object_name, child_object_name, self.template_name_suffix))
            names.insert(0, "%s/%s_%s%s.html" % (parent_app, parent_object_name, child_object_name, self.template_name_suffix))

        return names


class ProcessMultipleFormsMixin(object):
    """
    Modify GET and POST behaviour to construct and process
    multiple forms in one go. There's always a primary form,
    which is a ModelForm.

    By the time secondary forms are saved, self.new_object on the
    view will contain the primary object, ie the object that
    the primary form operates on.

    You can use it with `BoundCreateView`, and you just create
    a `bound_object_form` in `get_forms`:

    def get_forms(self):
        return {
            'child': bound_object_form(
                Child,
                field='parent',
                initial=lambda: self.new_object,
                )(
                prefix='child',
                **self.get_form_kwargs(),
                )
            }
    """

    def get_forms(self):
        raise ImproperlyConfigured(
            "ProcessMultipleFormsMixin must have get_forms overridden."
            )

    def get_context_data(self):
        form = self.get_form(self.get_form_class())
        forms = self.get_forms()
        ctx = super(ProcessMultipleFormsMixin, self).get_context_data()
        ctx.update(
            {
                'form': form,
                'forms': forms,
                }
            )
        return ctx

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        form = self.get_form(self.get_form_class())
        forms = self.get_forms()
        if form.is_valid() and all(
            map(
                lambda f: f.is_valid(), forms.values()
                )
            ):
            # in case we have M2M to something that's created
            # by one of the subforms, we need to separate out
            # core object saving (and hence creation) from the
            # save_m2m step. (ModelForms are designed to support
            # this.)
            #
            # We stash the object created by the primary form in
            # self.new_object rather than self.object so it can
            # be used with BoundCreateView, where self.object
            # is the parent not the freshly-created child. It is
            # however a slightly confusing name when used for
            # edit/update functionality.
            self.new_object = form.save(commit=False)
            self.new_object.save()
            sub_objects = [ f.save() for f in forms.values() ]
            #print sub_objects
            #print [ o.pk for o in sub_objects ]
            form.save_m2m()
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data())

    def get_form_kwargs(self):
        kwargs = super(ProcessMultipleFormsMixin, self).get_form_kwargs()
        #print "get_form_kwargs", kwargs
        return kwargs


class MultipleFormsUpdateView(ProcessMultipleFormsMixin, UpdateView):
    """
    Like django.views.generic.edit.UpdateView, but coping with
    multiple forms using the above mixin. Use as:

    class MyUpdateView(MultipleFormsUpdateView):
        queryset = MyModel.objects.all()

        def get_forms(self):
            return {
                'child': bound_object_form(
                    Child,
                    field='parent',
                    initial=lambda: self.new_object,
                    )(
                    prefix='child',
                    **self.get_form_kwargs(),
                )
            }

    Will use the app/model_form.html template by default.
    """

    template_name_suffix = '_form'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(MultipleFormsUpdateView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(MultipleFormsUpdateView, self).post(request, *args, **kwargs)


class MultiBoundObjectFormsMixin(object):
    """
    A simple way of specifying bound object forms for
    ProcessMultipleFormsMixin.

    You set `forms_models` to a list of either models or dictionaries
    with model, field_name, queryset and other things passed as kwargs to
    `bound_object_formset` (and hence to `modelformset_factory`).

    field_name is the name of the ForeignKey from the model to its
    parent and queryset is the reverse. Both can be auto-detected from
    the first ForeignKey on the model.
    """

    forms_models = []

    def get_forms(self):
        forms = {}
        for model_conf in self.forms_models:
            if isinstance(model_conf, dict):
                model = model_conf['model']
                foreign_key_field = model_conf.get('field_name', None)
                queryset = model_conf.get('queryset', None)
                factory_kwargs = dict(model_conf) # clone it!
                del factory_kwargs['model']
                if 'field_name' in factory_kwargs:
                    del factory_kwargs['field_name']
                if 'queryset' in factory_kwargs:
                    del factory_kwargs['queryset']
            else:
                factory_kwargs = {}
                model = model_conf
                foreign_key_field = None
                queryset = None
            if foreign_key_field is None:
                # try to auto-detect, just use the first ForeignKey
                # in the model
                for field in model._meta.fields:
                    if isinstance(field, models.ForeignKey):
                        foreign_key_field = field.name
                if foreign_key_field is None:
                    raise ImproperlyConfigured(
                        "MultiBoundObjectFormsMixin.forms_models must contain either models with a ForeignKey or a dictionary of configuration."
                        )
            if queryset is None:
                if not hasattr(self, 'object') or self.object is None:
                    queryset = model.objects.none()
                else:
                    queryset = model.objects.filter(
                        **{
                            foreign_key_field: self.object,
                            }
                          )

            forms[model._meta.object_name.lower()] = bound_object_formset(
                model,
                queryset=queryset,
                field=foreign_key_field,
                initial=lambda: self.new_object,
                **factory_kwargs
                )(
                prefix=model._meta.object_name.lower(),
                **FormMixin.get_form_kwargs(self)
                )

        return forms


class MultiUpdateView(MultiBoundObjectFormsMixin, MultipleFormsUpdateView):
    """
    Set queryset/model, form_class (for the primary object), and
    forms_models as described for MultiBoundObjectFormsMixin (or
    implement get_forms yourself).
    """
    pass


class MultiBoundCreateView(MultiBoundObjectFormsMixin, ProcessMultipleFormsMixin, BoundCreateView):
    """
    Set model (of child), queryset (of parent), form_class (of child),
    and forms_models as described for MultiBoundObjectFormsMixin (or
    implement get_forms yourself).
    """
    pass


class MultiCreateView(MultiBoundObjectFormsMixin, ProcessMultipleFormsMixin, CreateView):
    """Set model, form_class and forms_models."""
    
    template_name_suffix = '_create'
    object = None

    def get_success_url(self):
        self.object = self.new_object
        return super(MultiCreateView, self).get_success_url()
