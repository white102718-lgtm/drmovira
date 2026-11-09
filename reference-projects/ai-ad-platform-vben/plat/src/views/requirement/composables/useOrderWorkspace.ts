import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Modal } from 'ant-design-vue';

export type WorkspaceView = 'accept' | 'detail' | 'form' | 'list';

/** 工单页内工作台：列表 / 需求详情 / 验收详情 / 新建·编辑 视图状态机，状态同步 URL（replace 不压历史栈） */
export function useOrderWorkspace(options: {
  acceptStatuses: string[];
  onBackToList?: () => void;
}) {
  const router = useRouter();
  const route = useRoute();

  function qv(value: unknown) {
    return String((Array.isArray(value) ? value[0] : value) ?? '');
  }

  const view = ref<WorkspaceView>('list');

  // 详情上下文；验收已统一迁移到任务中心。
  const currentId = ref('');
  const currentTitle = ref('');
  const currentStatus = ref('');
  const mountedDetail = ref(false);
  const mountedAccept = ref(false);

  // 表单上下文（新建 / 编辑）
  const formOpen = ref(false);
  const formMode = ref<'edit' | 'new'>('new');
  const formId = ref('');
  const formNo = ref('');
  const formGen = ref(0);

  // 从 URL 恢复视图（刷新 / 新窗口打开）
  {
    const v = qv(route.query.view);
    const id = qv(route.query.id);
    if (v === 'accept' && id) {
      void router.replace({
        path: '/workbench/tasks',
        query: { materialOrderId: id },
      });
    } else if (v === 'detail' && id) {
      currentId.value = id;
      mountedDetail.value = true;
      view.value = v;
    } else if (v === 'form') {
      formOpen.value = true;
      formMode.value = qv(route.query.mode) === 'edit' && id ? 'edit' : 'new';
      formId.value = formMode.value === 'edit' ? id : '';
      view.value = 'form';
    }
  }

  const detailOpen = computed(() => !!currentId.value);
  const acceptTabVisible = computed(
    () =>
      detailOpen.value &&
      (mountedAccept.value ||
        options.acceptStatuses.includes(currentStatus.value)),
  );
  const formTabLabel = computed(() =>
    formMode.value === 'new'
      ? '新建需求'
      : `编辑${formNo.value ? ` #${formNo.value}` : ''}`,
  );

  // 视图状态同步到 URL（replace，不压历史栈；分享/刷新/Ctrl+点击 可还原）
  watch([view, currentId, formMode, formId], () => {
    const query: Record<string, any> = { ...route.query };
    delete query.view;
    delete query.id;
    delete query.mode;
    if (view.value === 'detail' || view.value === 'accept') {
      query.view = view.value;
      query.id = currentId.value;
    } else if (view.value === 'form') {
      query.view = 'form';
      query.mode = formMode.value;
      if (formId.value) query.id = formId.value;
    }
    router.replace({ query });
  });

  // 详情/表单里的操作可能改变工单状态，回列表时刷新
  watch(view, (v) => {
    if (v === 'list') options.onBackToList?.();
  });

  function openDetail(row: any, target: 'accept' | 'detail') {
    if (target === 'accept') {
      void router.push({
        path: '/workbench/tasks',
        query: { materialOrderId: qv(row._rawId) },
      });
      return;
    }
    if (currentId.value !== row._rawId) {
      currentId.value = row._rawId;
      currentTitle.value = qv(row.title);
      currentStatus.value = qv(row.status);
      mountedDetail.value = false;
      mountedAccept.value = false;
    }
    // 需求详情/验收详情一起挂载，两个菜单项同时出现（验收仅在状态支持时）
    mountedDetail.value = true;
    if (options.acceptStatuses.includes(currentStatus.value)) {
      mountedAccept.value = true;
    }
    view.value = target;
  }

  function openDetailTab() {
    mountedDetail.value = true;
    view.value = 'detail';
  }

  function openAcceptTab() {
    if (!currentId.value) return;
    void router.push({
      path: '/workbench/tasks',
      query: { materialOrderId: currentId.value },
    });
  }

  function onDetailLoaded(info: {
    orderNo: string;
    status: string;
    title: string;
  }) {
    if (info.title) currentTitle.value = info.title;
    if (info.status) currentStatus.value = info.status;
    // URL 恢复等入口只挂了单边，状态确认后把另一边也挂上
    if (options.acceptStatuses.includes(currentStatus.value))
      mountedAccept.value = true;
  }

  function onFormLoaded(info: { orderNo: string }) {
    if (info.orderNo) formNo.value = info.orderNo;
  }

  function doOpenForm(mode: 'edit' | 'new', row?: any) {
    formOpen.value = true;
    formMode.value = mode;
    formId.value = mode === 'edit' ? row._rawId : '';
    formNo.value = mode === 'edit' ? qv(row.id) : '';
    formGen.value++;
    view.value = 'form';
  }

  function confirmDiscardForm(onOk: () => void) {
    Modal.confirm({
      title:
        formMode.value === 'new'
          ? '放弃当前新建的需求？'
          : `放弃正在编辑的需求${formNo.value ? ` #${formNo.value}` : ''}？`,
      content: '未提交的修改将丢失。',
      okText: '放弃',
      cancelText: '取消',
      onOk,
    });
  }

  function openForm(mode: 'edit' | 'new', row?: any) {
    const sameCtx =
      formOpen.value &&
      formMode.value === mode &&
      (mode === 'new' || formId.value === row._rawId);
    if (sameCtx) {
      view.value = 'form';
      return;
    }
    if (formOpen.value) {
      confirmDiscardForm(() => doOpenForm(mode, row));
      return;
    }
    doOpenForm(mode, row);
  }

  function closeForm() {
    confirmDiscardForm(() => {
      formOpen.value = false;
      if (view.value === 'form') view.value = 'list';
    });
  }

  // 表单提交成功后回列表
  function handleFormDone() {
    formOpen.value = false;
    view.value = 'list';
  }

  // Ctrl/中键点击时在浏览器新标签页打开对应视图
  function viewHref(target: 'accept' | 'detail', row: any) {
    if (target === 'accept') {
      return router.resolve({
        path: '/workbench/tasks',
        query: { materialOrderId: qv(row._rawId) },
      }).href;
    }
    return router.resolve({
      path: route.path,
      query: { view: target, id: row._rawId },
    }).href;
  }

  function tabClass(active: boolean) {
    return active
      ? 'bg-blue-50 text-blue-600'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900';
  }

  return reactive({
    view,
    currentId,
    currentTitle,
    currentStatus,
    mountedDetail,
    mountedAccept,
    detailOpen,
    acceptTabVisible,
    formOpen,
    formMode,
    formId,
    formNo,
    formGen,
    formTabLabel,
    openDetail,
    openDetailTab,
    openAcceptTab,
    onDetailLoaded,
    onFormLoaded,
    openForm,
    closeForm,
    handleFormDone,
    viewHref,
    tabClass,
  });
}

export type OrderWorkspace = ReturnType<typeof useOrderWorkspace>;
