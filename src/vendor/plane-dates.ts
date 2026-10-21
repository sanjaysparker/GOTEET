/** Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * Extracted from makeplane/plane apps/web/components/gantt-chart/views/helpers.ts
 * Revision 6c16585c81bac84d8ce67110c70a69b1bf07f10b. License: public/licenses/plane-AGPL-3.0.txt.
 */
export const getNumberOfDaysBetweenTwoDates = (startDate: Date, endDate: Date) => {
  let daysDifference: number = 0;
  startDate.setHours(0, 0, 0, 0);
  endDate.setHours(0, 0, 0, 0);

  const timeDifference: number = startDate.getTime() - endDate.getTime();
  daysDifference = Math.round(timeDifference / (1000 * 60 * 60 * 24));

  return daysDifference;
};
