<script lang="ts" setup>
interface Props {
  companyName?: string;
  companySiteLink?: string;
  date?: string;
  icp?: string;
  icpLink?: string;
}

defineOptions({
  name: 'Copyright',
});

withDefaults(defineProps<Props>(), {
  companyName: 'Vben Admin',
  companySiteLink: '',
  date: '2024',
  icp: '',
  icpLink: '',
});
</script>

<template>
  <div class="text-md flex-center">
    <!-- ICP Link -->
    <a
      v-if="icp"
      :href="icpLink || 'javascript:void(0)'"
      class="hover:text-primary-hover mx-1"
      target="_blank"
    >
      {{ icp }}
    </a>

    <!--    &lt;!&ndash; Copyright Text &ndash;&gt;-->
    <!--    Copyright © {{ date }}-->

    <!--    &lt;!&ndash; Company Link &ndash;&gt;-->
    <!--    <a-->
    <!--      v-if="companyName"-->
    <!--      :href="companySiteLink || 'javascript:void(0)'"-->
    <!--      class="hover:text-primary-hover mx-1"-->
    <!--      target="_blank"-->
    <!--    >-->
    <!--      {{ companyName }}-->
    <!--    </a>-->
  </div>
</template>
